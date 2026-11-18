from datetime import date, timedelta
import importlib
import os
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


VALID_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00"
    b"\x18\xdd\x8d\xb0"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)

VALID_PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_tracker.db"
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("TRACKER_DB_PATH", str(db_path))
    monkeypatch.setenv("TRACKER_UPLOADS_DIR", str(uploads_dir))

    for mod_name in ["app.config", "app.db", "app.models", "app.security", "app.services", "app.notifier", "app.main"]:
        if mod_name in sys.modules:
            importlib.reload(sys.modules[mod_name])

    app_main = importlib.import_module("app.main")
    app = getattr(app_main, "app")

    with TestClient(app) as test_client:
        yield test_client


def test_health_and_security_headers(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"

    headers = {k.lower(): v for k, v in resp.headers.items()}
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("x-frame-options") in ("DENY", "SAMEORIGIN")
    assert "content-security-policy" in headers

    index_resp = client.get("/")
    assert index_resp.status_code == 200
    assert "text/html" in index_resp.headers.get("content-type", "")


def test_subscription_lifecycle_and_advance(client):
    today = date.today()
    next_date = today + timedelta(days=2)

    create_payload = {
        "name": "Yandex Plus",
        "category": "Streaming",
        "amount": 299.0,
        "currency": "RUB",
        "billing_cycle": "monthly",
        "next_billing_date": next_date.isoformat(),
        "remind_days_before": 3,
        "status": "active",
        "cancel_url": "https://plus.yandex.ru/my",
        "notes": "Family plan",
    }
    resp = client.post("/api/subscriptions", json=create_payload)
    assert resp.status_code in (200, 201), resp.text
    sub = resp.json()
    sub_id = sub["id"]
    assert sub["name"] == "Yandex Plus"
    assert float(sub["amount"]) == 299.0
    assert sub["status"] == "active"

    list_resp = client.get("/api/subscriptions")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["id"] == sub_id

    adv_resp = client.post(f"/api/subscriptions/{sub_id}/advance")
    assert adv_resp.status_code == 200, adv_resp.text
    advanced_sub = adv_resp.json()
    assert advanced_sub["next_billing_date"] > next_date.isoformat()

    status_resp = client.post(
        f"/api/subscriptions/{sub_id}/status",
        json={"status": "paused"},
    )
    assert status_resp.status_code == 200, status_resp.text
    assert status_resp.json()["status"] == "paused"

    paused_list = client.get("/api/subscriptions", params={"status": "paused"}).json()
    assert len(paused_list) == 1
    active_list = client.get("/api/subscriptions", params={"status": "active"}).json()
    assert len(active_list) == 0

    del_resp = client.delete(f"/api/subscriptions/{sub_id}")
    assert del_resp.status_code in (200, 204)
    assert len(client.get("/api/subscriptions").json()) == 0


def test_summary_and_upcoming_reminders(client):
    today = date.today()

    r1 = client.post(
        "/api/subscriptions",
        json={
            "name": "Music Service",
            "category": "Music",
            "amount": 200.0,
            "currency": "RUB",
            "billing_cycle": "monthly",
            "next_billing_date": (today + timedelta(days=2)).isoformat(),
            "remind_days_before": 5,
            "status": "active",
        },
    )
    assert r1.status_code in (200, 201), r1.text

    r2 = client.post(
        "/api/subscriptions",
        json={
            "name": "Cloud Yearly",
            "category": "Cloud",
            "amount": 1200.0,
            "currency": "RUB",
            "billing_cycle": "yearly",
            "next_billing_date": (today + timedelta(days=60)).isoformat(),
            "remind_days_before": 3,
            "status": "active",
        },
    )
    assert r2.status_code in (200, 201), r2.text

    r3 = client.post(
        "/api/subscriptions",
        json={
            "name": "Paused Gym",
            "category": "Sport",
            "amount": 1500.0,
            "currency": "RUB",
            "billing_cycle": "monthly",
            "next_billing_date": (today + timedelta(days=1)).isoformat(),
            "remind_days_before": 5,
            "status": "paused",
        },
    )
    assert r3.status_code in (200, 201), r3.text

    w1 = client.post(
        "/api/warranties",
        data={
            "item_name": "SSD NVMe 1TB",
            "store": "DNS",
            "purchase_date": (today - timedelta(days=355)).isoformat(),
            "warranty_end_date": (today + timedelta(days=10)).isoformat(),
            "price": "7990",
            "currency": "RUB",
            "serial_number": "SN-998877",
            "remind_days_before": "14",
            "notes": "5 year controller",
        },
    )
    assert w1.status_code in (200, 201), w1.text

    summary_resp = client.get("/api/summary")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()

    assert pytest.approx(float(summary["monthly_total"]), rel=1e-2) == 300.0
    assert pytest.approx(float(summary["yearly_total"]), rel=1e-2) == 3600.0
    assert summary["active_subscriptions_count"] == 2
    assert summary["warranties_count"] == 1
    assert len(summary["upcoming_subscriptions"]) == 1
    assert summary["upcoming_subscriptions"][0]["name"] == "Music Service"
    assert len(summary["expiring_warranties"]) == 1
    assert summary["expiring_warranties"][0]["item_name"] == "SSD NVMe 1TB"


def test_warranty_receipt_upload_and_reject_malicious(client):
    today = date.today()
    base_data = {
        "item_name": "Monitor 27",
        "store": "Citilink",
        "purchase_date": today.isoformat(),
        "warranty_end_date": (today + timedelta(days=365)).isoformat(),
        "price": "24990",
        "currency": "RUB",
        "serial_number": "MON-12345",
        "remind_days_before": "14",
        "notes": "IPS panel",
    }

    ok_png = client.post(
        "/api/warranties",
        data=base_data,
        files={"receipt": ("receipt.png", VALID_PNG_BYTES, "image/png")},
    )
    assert ok_png.status_code in (200, 201), ok_png.text
    warranty_id = ok_png.json()["id"]

    dl_resp = client.get(f"/api/warranties/{warranty_id}/receipt")
    assert dl_resp.status_code == 200
    assert dl_resp.content == VALID_PNG_BYTES

    ok_pdf = client.post(
        "/api/warranties",
        data=base_data,
        files={"receipt": ("invoice.pdf", VALID_PDF_BYTES, "application/pdf")},
    )
    assert ok_pdf.status_code in (200, 201), ok_pdf.text

    bad_exe = client.post(
        "/api/warranties",
        data=base_data,
        files={"receipt": ("malware.exe", b"MZ\x90\x00\x03\x00\x00\x00", "application/octet-stream")},
    )
    assert bad_exe.status_code in (400, 422)

    bad_html = client.post(
        "/api/warranties",
        data=base_data,
        files={"receipt": ("xss.html", b"<script>alert(1)</script>", "text/html")},
    )
    assert bad_html.status_code in (400, 422)

    fake_mime = client.post(
        "/api/warranties",
        data=base_data,
        files={"receipt": ("fake.png", b"not a real png file content", "image/png")},
    )
    assert fake_mime.status_code in (400, 422)

    del_resp = client.delete(f"/api/warranties/{warranty_id}")
    assert del_resp.status_code in (200, 204)
    after_del = client.get(f"/api/warranties/{warranty_id}/receipt")
    assert after_del.status_code == 404


def test_reject_dangerous_cancel_url_and_path_traversal(client):
    today = date.today()
    for bad_url in [
        "javascript:alert(1)",
        "JAVASCRIPT:alert(document.cookie)",
        "data:text/html,<script>alert(1)</script>",
        "ftp://files.example.com/cancel",
    ]:
        resp = client.post(
            "/api/subscriptions",
            json={
                "name": "Bad URL Sub",
                "category": "Other",
                "amount": 100.0,
                "currency": "RUB",
                "billing_cycle": "monthly",
                "next_billing_date": (today + timedelta(days=10)).isoformat(),
                "remind_days_before": 3,
                "status": "active",
                "cancel_url": bad_url,
            },
        )
        assert resp.status_code in (400, 422), f"URL {bad_url} should be rejected"

    traversal_upload = client.post(
        "/api/warranties",
        data={
            "item_name": "Router",
            "store": "Shop",
            "purchase_date": today.isoformat(),
            "warranty_end_date": (today + timedelta(days=365)).isoformat(),
            "price": "3500",
            "currency": "RUB",
        },
        files={"receipt": ("../../evil.png", VALID_PNG_BYTES, "image/png")},
    )
    if traversal_upload.status_code in (200, 201):
        saved_filename = traversal_upload.json().get("receipt_filename", "")
        assert ".." not in saved_filename
        assert "/" not in saved_filename
        assert "\\" not in saved_filename
    else:
        assert traversal_upload.status_code in (400, 422)


def test_update_subscription_custom_days_and_notifications(client):
    today = date.today()
    create_resp = client.post(
        "/api/subscriptions",
        json={
            "name": "VPN Custom",
            "category": "Security",
            "amount": 150.0,
            "currency": "RUB",
            "billing_cycle": "custom_days",
            "cycle_days": 15,
            "next_billing_date": (today + timedelta(days=1)).isoformat(),
            "remind_days_before": 3,
            "status": "active",
        },
    )
    assert create_resp.status_code in (200, 201), create_resp.text
    sub_id = create_resp.json()["id"]

    update_resp = client.put(
        f"/api/subscriptions/{sub_id}",
        json={
            "name": "VPN Custom Pro",
            "category": "Security",
            "amount": 300.0,
            "currency": "RUB",
            "billing_cycle": "custom_days",
            "cycle_days": 15,
            "next_billing_date": (today + timedelta(days=1)).isoformat(),
            "remind_days_before": 3,
            "status": "active",
        },
    )
    assert update_resp.status_code == 200, update_resp.text
    assert update_resp.json()["name"] == "VPN Custom Pro"

    adv_resp = client.post(f"/api/subscriptions/{sub_id}/advance")
    assert adv_resp.status_code == 200
    assert adv_resp.json()["next_billing_date"] == (today + timedelta(days=16)).isoformat()

    notif_resp = client.post("/api/notifications/check")
    assert notif_resp.status_code == 200

    css_resp = client.get("/static/styles.css")
    assert css_resp.status_code == 200
    js_resp = client.get("/static/app.js")
    assert js_resp.status_code == 200


def test_reject_oversized_receipt(client):
    today = date.today()
    oversized_png = VALID_PNG_BYTES + (b"\x00" * (5 * 1024 * 1024 + 1024))
    resp = client.post(
        "/api/warranties",
        data={
            "item_name": "Laptop",
            "store": "Store",
            "purchase_date": today.isoformat(),
            "warranty_end_date": (today + timedelta(days=365)).isoformat(),
            "price": "50000",
            "currency": "RUB",
        },
        files={"receipt": ("huge.png", oversized_png, "image/png")},
    )
    assert resp.status_code in (400, 413, 422)

