from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, File, Form, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import BASE_DIR, get_settings
from app.db import get_db, get_session_factory, init_db
from app.notifier import run_notifications_check
from app.schemas import (
    NotificationCheckOut,
    SubscriptionCreate,
    SubscriptionOut,
    SubscriptionStatusUpdate,
    SubscriptionUpdate,
    SummaryOut,
    WarrantyOut,
)
from app.security import generate_csrf_token, resolve_receipt_path, sanitize_display_filename
from app.services import (
    advance_subscription_date,
    change_subscription_status,
    create_subscription,
    create_warranty,
    delete_subscription,
    delete_warranty,
    get_summary,
    get_warranty_or_404,
    list_subscriptions,
    list_warranties,
    update_subscription,
)

STATIC_DIR = BASE_DIR / "app" / "static"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _scheduled_job() -> None:
    settings = get_settings()
    factory = get_session_factory(settings.db_path)
    with factory() as session:
        run_notifications_check(session, send_external=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    init_db(settings.db_path)
    scheduler: BackgroundScheduler | None = None
    if settings.enable_scheduler:
        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(
            _scheduled_job,
            "interval",
            minutes=settings.check_interval_minutes,
            id="reminder_check",
            replace_existing=True,
        )
        scheduler.start()
    try:
        yield
    finally:
        if scheduler is not None and scheduler.running:
            scheduler.shutdown(wait=False)


app = FastAPI(
    title="Subscription & Warranty Tracker",
    description="Локальный сервис учета регулярных подписок, чеков и сроков гарантии.",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'; "
    "form-action 'self'"
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = CSP_POLICY
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request):
    csrf_token = request.cookies.get("csrf_token") or generate_csrf_token()
    index_template = TEMPLATES_DIR / "index.html"
    if index_template.is_file():
        response = templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"csrf_token": csrf_token},
        )
    else:
        response = HTMLResponse(
            content="<!DOCTYPE html><html lang='ru'><head><meta charset='utf-8'><title>Трекер подписок и гарантий</title></head><body><h1>Трекер подписок и гарантий</h1></body></html>"
        )
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        samesite="lax",
        secure=False,
    )
    return response


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/summary", response_model=SummaryOut)
def api_get_summary(db: Annotated[Session, Depends(get_db)]) -> SummaryOut:
    return get_summary(db)


@app.get("/api/subscriptions", response_model=list[SubscriptionOut])
def api_list_subscriptions(
    db: Annotated[Session, Depends(get_db)],
    status: Annotated[str | None, Query()] = None,
) -> list[SubscriptionOut]:
    return list_subscriptions(db, status_filter=status)


@app.post(
    "/api/subscriptions",
    response_model=SubscriptionOut,
    status_code=status.HTTP_201_CREATED,
)
def api_create_subscription(
    payload: SubscriptionCreate,
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionOut:
    return create_subscription(db, payload)


@app.put("/api/subscriptions/{subscription_id}", response_model=SubscriptionOut)
def api_update_subscription(
    subscription_id: int,
    payload: SubscriptionUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionOut:
    return update_subscription(db, subscription_id, payload)


@app.post("/api/subscriptions/{subscription_id}/advance", response_model=SubscriptionOut)
def api_advance_subscription(
    subscription_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionOut:
    return advance_subscription_date(db, subscription_id)


@app.post("/api/subscriptions/{subscription_id}/status", response_model=SubscriptionOut)
def api_change_subscription_status(
    subscription_id: int,
    payload: SubscriptionStatusUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionOut:
    return change_subscription_status(db, subscription_id, payload.status)


@app.delete("/api/subscriptions/{subscription_id}")
def api_delete_subscription(
    subscription_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str | int]:
    delete_subscription(db, subscription_id)
    return {"status": "deleted", "id": subscription_id}


@app.get("/api/warranties", response_model=list[WarrantyOut])
def api_list_warranties(
    db: Annotated[Session, Depends(get_db)],
) -> list[WarrantyOut]:
    return list_warranties(db)


@app.post(
    "/api/warranties",
    response_model=WarrantyOut,
    status_code=status.HTTP_201_CREATED,
)
async def api_create_warranty(
    db: Annotated[Session, Depends(get_db)],
    item_name: Annotated[str, Form(...)],
    purchase_date: Annotated[date, Form(...)],
    warranty_end_date: Annotated[date, Form(...)],
    store: Annotated[str | None, Form()] = None,
    price: Annotated[float, Form()] = 0.0,
    currency: Annotated[str, Form()] = "RUB",
    serial_number: Annotated[str | None, Form()] = None,
    remind_days_before: Annotated[int, Form()] = 14,
    notes: Annotated[str | None, Form()] = None,
    receipt: Annotated[UploadFile | None, File()] = None,
) -> WarrantyOut:
    settings = get_settings()
    return await create_warranty(
        db,
        item_name=item_name,
        store=store,
        purchase_date=purchase_date,
        warranty_end_date=warranty_end_date,
        price=price,
        currency=currency,
        serial_number=serial_number,
        remind_days_before=remind_days_before,
        notes=notes,
        receipt=receipt,
        uploads_dir=settings.uploads_dir,
        max_upload_bytes=settings.max_upload_bytes,
    )


@app.get("/api/warranties/{warranty_id}/receipt")
def api_get_warranty_receipt(
    warranty_id: int,
    db: Annotated[Session, Depends(get_db)],
    download: Annotated[bool, Query()] = False,
) -> FileResponse:
    settings = get_settings()
    item = get_warranty_or_404(db, warranty_id)
    file_path, media_type = resolve_receipt_path(settings.uploads_dir, item.receipt_filename)
    display_name = sanitize_display_filename(item.receipt_original_name or file_path.name)
    disposition_type = "attachment" if download else "inline"
    encoded_name = quote(display_name)
    headers = {
        "Content-Disposition": f"{disposition_type}; filename*=UTF-8''{encoded_name}",
    }
    return FileResponse(
        path=file_path,
        media_type=media_type,
        headers=headers,
    )


@app.delete("/api/warranties/{warranty_id}")
def api_delete_warranty(
    warranty_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str | int]:
    settings = get_settings()
    delete_warranty(db, warranty_id, settings.uploads_dir)
    return {"status": "deleted", "id": warranty_id}


@app.post("/api/notifications/check", response_model=NotificationCheckOut)
def api_check_notifications(
    db: Annotated[Session, Depends(get_db)],
) -> NotificationCheckOut:
    return run_notifications_check(db, send_external=True)
