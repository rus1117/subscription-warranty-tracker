from datetime import date, datetime, timezone
import logging
import httpx
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.schemas import NotificationCheckOut
from app.services import get_summary

logger = logging.getLogger("tracker.notifier")


def build_notification_messages(
    db: Session,
    today: date | None = None,
) -> tuple[list[str], NotificationCheckOut]:
    summary = get_summary(db, today=today)
    messages: list[str] = []

    for sub in summary.upcoming_subscriptions:
        messages.append(
            f"Подписка «{sub.name}»: списание {sub.amount:.2f} {sub.currency} "
            f"({sub.next_billing_date.isoformat()}, осталось дн.: {sub.days_until_billing})"
        )

    for item in summary.expiring_warranties:
        messages.append(
            f"Гарантия на «{item.item_name}»: истекает {item.warranty_end_date.isoformat()} "
            f"(осталось дн.: {item.days_left})"
        )

    settings = get_settings()
    telegram_configured = bool(settings.telegram_bot_token and settings.telegram_chat_id)

    result = NotificationCheckOut(
        checked_at=datetime.now(timezone.utc),
        upcoming_subscriptions=summary.upcoming_subscriptions,
        expiring_warranties=summary.expiring_warranties,
        alerts_count=summary.alerts_count,
        messages=messages,
        telegram_configured=telegram_configured,
        telegram_sent=False,
    )
    return messages, result


def send_telegram_alert(text: str, settings: Settings) -> bool:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return False
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        response = httpx.post(
            url,
            json={
                "chat_id": settings.telegram_chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=10.0,
        )
        return response.status_code == 200
    except httpx.HTTPError as exc:
        logger.warning("Ошибка отправки уведомления в Telegram: %s", exc)
        return False


def run_notifications_check(
    db: Session,
    today: date | None = None,
    send_external: bool = True,
) -> NotificationCheckOut:
    settings = get_settings()
    messages, result = build_notification_messages(db, today=today)
    if send_external and messages and result.telegram_configured:
        text_body = "Напоминания о подписках и гарантиях:\n\n" + "\n".join(
            f"- {msg}" for msg in messages
        )
        result.telegram_sent = send_telegram_alert(text_body, settings)
    return result
