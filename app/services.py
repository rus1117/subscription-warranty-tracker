from datetime import date, timedelta
from pathlib import Path
from dateutil.relativedelta import relativedelta
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Subscription, WarrantyItem
from app.schemas import (
    SubscriptionCreate,
    SubscriptionOut,
    SubscriptionUpdate,
    SummaryOut,
    WarrantyOut,
)
from app.security import safe_delete_receipt, validate_and_store_receipt


def calculate_subscription_equivalents(
    amount: float,
    billing_cycle: str,
    cycle_days: int | None,
) -> tuple[float, float]:
    if billing_cycle == "monthly":
        monthly = amount
        yearly = amount * 12.0
    elif billing_cycle == "yearly":
        monthly = amount / 12.0
        yearly = amount
    elif billing_cycle == "custom_days":
        days = cycle_days if (cycle_days and cycle_days > 0) else 30
        monthly = amount * (30.0 / days)
        yearly = amount * (365.0 / days)
    else:
        monthly = amount
        yearly = amount * 12.0
    return round(monthly, 2), round(yearly, 2)


def serialize_subscription(sub: Subscription, today: date | None = None) -> SubscriptionOut:
    ref_date = today or date.today()
    days_until = (sub.next_billing_date - ref_date).days
    monthly_eq, yearly_eq = calculate_subscription_equivalents(
        sub.amount,
        sub.billing_cycle,
        sub.cycle_days,
    )
    is_due_soon = sub.status == "active" and 0 <= days_until <= sub.remind_days_before
    return SubscriptionOut(
        id=sub.id,
        name=sub.name,
        category=sub.category,
        amount=round(float(sub.amount), 2),
        currency=sub.currency,
        billing_cycle=sub.billing_cycle,
        cycle_days=sub.cycle_days,
        next_billing_date=sub.next_billing_date,
        remind_days_before=sub.remind_days_before,
        status=sub.status,
        cancel_url=sub.cancel_url,
        notes=sub.notes,
        days_until_billing=days_until,
        monthly_equivalent=monthly_eq,
        yearly_equivalent=yearly_eq,
        is_due_soon=is_due_soon,
        created_at=sub.created_at,
    )


def serialize_warranty(item: WarrantyItem, today: date | None = None) -> WarrantyOut:
    ref_date = today or date.today()
    days_left = (item.warranty_end_date - ref_date).days
    is_expired = days_left < 0
    is_expiring_soon = 0 <= days_left <= item.remind_days_before
    return WarrantyOut(
        id=item.id,
        item_name=item.item_name,
        store=item.store,
        purchase_date=item.purchase_date,
        warranty_end_date=item.warranty_end_date,
        price=round(float(item.price), 2),
        currency=item.currency,
        serial_number=item.serial_number,
        receipt_filename=item.receipt_filename,
        receipt_original_name=item.receipt_original_name,
        has_receipt=bool(item.receipt_filename),
        remind_days_before=item.remind_days_before,
        notes=item.notes,
        days_left=days_left,
        is_expired=is_expired,
        is_expiring_soon=is_expiring_soon,
        created_at=item.created_at,
    )


def list_subscriptions(
    db: Session,
    status_filter: str | None = None,
    today: date | None = None,
) -> list[SubscriptionOut]:
    stmt = select(Subscription).order_by(Subscription.next_billing_date.asc(), Subscription.id.asc())
    if status_filter and status_filter != "all":
        stmt = stmt.where(Subscription.status == status_filter)
    rows = db.scalars(stmt).all()
    ref_date = today or date.today()
    return [serialize_subscription(sub, ref_date) for sub in rows]


def get_subscription_or_404(db: Session, subscription_id: int) -> Subscription:
    sub = db.get(Subscription, subscription_id)
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Подписка не найдена.",
        )
    return sub


def create_subscription(db: Session, payload: SubscriptionCreate) -> SubscriptionOut:
    sub = Subscription(
        name=payload.name,
        category=payload.category,
        amount=payload.amount,
        currency=payload.currency,
        billing_cycle=payload.billing_cycle,
        cycle_days=payload.cycle_days if payload.billing_cycle == "custom_days" else None,
        next_billing_date=payload.next_billing_date,
        remind_days_before=payload.remind_days_before,
        status=payload.status,
        cancel_url=payload.cancel_url,
        notes=payload.notes.strip() if payload.notes else None,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return serialize_subscription(sub)


def update_subscription(
    db: Session,
    subscription_id: int,
    payload: SubscriptionUpdate,
) -> SubscriptionOut:
    sub = get_subscription_or_404(db, subscription_id)
    update_data = payload.model_dump(exclude_unset=True)

    for field_name, value in update_data.items():
        if field_name == "notes" and isinstance(value, str):
            value = value.strip() or None
        setattr(sub, field_name, value)

    if sub.billing_cycle == "custom_days":
        if not sub.cycle_days or sub.cycle_days < 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Для произвольного цикла (custom_days) необходимо указать cycle_days >= 1.",
            )
    else:
        sub.cycle_days = None

    db.commit()
    db.refresh(sub)
    return serialize_subscription(sub)


def advance_subscription_date(db: Session, subscription_id: int) -> SubscriptionOut:
    sub = get_subscription_or_404(db, subscription_id)
    if sub.billing_cycle == "monthly":
        sub.next_billing_date = sub.next_billing_date + relativedelta(months=+1)
    elif sub.billing_cycle == "yearly":
        sub.next_billing_date = sub.next_billing_date + relativedelta(years=+1)
    elif sub.billing_cycle == "custom_days":
        days = sub.cycle_days if (sub.cycle_days and sub.cycle_days > 0) else 30
        sub.next_billing_date = sub.next_billing_date + timedelta(days=days)
    else:
        sub.next_billing_date = sub.next_billing_date + relativedelta(months=+1)

    db.commit()
    db.refresh(sub)
    return serialize_subscription(sub)


def change_subscription_status(
    db: Session,
    subscription_id: int,
    new_status: str,
) -> SubscriptionOut:
    sub = get_subscription_or_404(db, subscription_id)
    sub.status = new_status
    db.commit()
    db.refresh(sub)
    return serialize_subscription(sub)


def delete_subscription(db: Session, subscription_id: int) -> None:
    sub = get_subscription_or_404(db, subscription_id)
    db.delete(sub)
    db.commit()


def list_warranties(db: Session, today: date | None = None) -> list[WarrantyOut]:
    stmt = select(WarrantyItem).order_by(WarrantyItem.warranty_end_date.asc(), WarrantyItem.id.asc())
    rows = db.scalars(stmt).all()
    ref_date = today or date.today()
    return [serialize_warranty(item, ref_date) for item in rows]


def get_warranty_or_404(db: Session, warranty_id: int) -> WarrantyItem:
    item = db.get(WarrantyItem, warranty_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Запись о гарантии не найдена.",
        )
    return item


async def create_warranty(
    db: Session,
    *,
    item_name: str,
    store: str | None,
    purchase_date: date,
    warranty_end_date: date,
    price: float,
    currency: str,
    serial_number: str | None,
    remind_days_before: int,
    notes: str | None,
    receipt: UploadFile | None,
    uploads_dir: Path,
    max_upload_bytes: int,
) -> WarrantyOut:
    cleaned_name = item_name.strip()
    if not cleaned_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Название товара не может быть пустым.",
        )
    if price < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Цена товара не может быть отрицательной.",
        )
    if remind_days_before < 0 or remind_days_before > 3650:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Некорректный срок напоминания.",
        )
    if warranty_end_date < purchase_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Дата окончания гарантии не может быть раньше даты покупки.",
        )

    stored_filename: str | None = None
    original_filename: str | None = None
    if receipt is not None and receipt.filename and receipt.filename.strip():
        stored_filename, original_filename = await validate_and_store_receipt(
            receipt,
            uploads_dir=uploads_dir,
            max_bytes=max_upload_bytes,
        )

    item = WarrantyItem(
        item_name=cleaned_name[:200],
        store=store.strip()[:200] if store and store.strip() else None,
        purchase_date=purchase_date,
        warranty_end_date=warranty_end_date,
        price=price,
        currency=(currency.strip()[:10] if currency and currency.strip() else "RUB"),
        serial_number=serial_number.strip()[:200] if serial_number and serial_number.strip() else None,
        receipt_filename=stored_filename,
        receipt_original_name=original_filename,
        remind_days_before=remind_days_before,
        notes=notes.strip()[:2000] if notes and notes.strip() else None,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return serialize_warranty(item)


def delete_warranty(db: Session, warranty_id: int, uploads_dir: Path) -> None:
    item = get_warranty_or_404(db, warranty_id)
    receipt_filename = item.receipt_filename
    db.delete(item)
    db.commit()
    if receipt_filename:
        safe_delete_receipt(uploads_dir, receipt_filename)


def get_summary(db: Session, today: date | None = None) -> SummaryOut:
    ref_date = today or date.today()
    subscriptions = db.scalars(
        select(Subscription).order_by(Subscription.next_billing_date.asc(), Subscription.id.asc())
    ).all()
    warranties = db.scalars(
        select(WarrantyItem).order_by(WarrantyItem.warranty_end_date.asc(), WarrantyItem.id.asc())
    ).all()

    monthly_total = 0.0
    yearly_total = 0.0
    active_count = 0
    paused_count = 0
    cancelled_count = 0
    upcoming_subscriptions: list[SubscriptionOut] = []

    for sub in subscriptions:
        serialized = serialize_subscription(sub, ref_date)
        if sub.status == "active":
            active_count += 1
            monthly_total += serialized.monthly_equivalent
            yearly_total += serialized.yearly_equivalent
            if 0 <= serialized.days_until_billing <= sub.remind_days_before:
                upcoming_subscriptions.append(serialized)
        elif sub.status == "paused":
            paused_count += 1
        elif sub.status == "cancelled":
            cancelled_count += 1

    expiring_warranties: list[WarrantyOut] = []
    active_warranties_count = 0
    for item in warranties:
        serialized_w = serialize_warranty(item, ref_date)
        if not serialized_w.is_expired:
            active_warranties_count += 1
        if 0 <= serialized_w.days_left <= item.remind_days_before:
            expiring_warranties.append(serialized_w)

    return SummaryOut(
        monthly_total=round(monthly_total, 2),
        yearly_total=round(yearly_total, 2),
        active_subscriptions_count=active_count,
        paused_subscriptions_count=paused_count,
        cancelled_subscriptions_count=cancelled_count,
        warranties_count=len(warranties),
        active_warranties_count=active_warranties_count,
        upcoming_subscriptions=upcoming_subscriptions,
        expiring_warranties=expiring_warranties,
        alerts_count=len(upcoming_subscriptions) + len(expiring_warranties),
    )
