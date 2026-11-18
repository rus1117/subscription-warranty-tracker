from dataclasses import dataclass
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv_if_present() -> None:
    env_file = BASE_DIR / ".env"
    if not env_file.is_file():
        return
    try:
        content = env_file.read_text(encoding="utf-8")
    except OSError:
        return
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv_if_present()


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    db_path: Path
    uploads_dir: Path
    enable_scheduler: bool
    check_interval_minutes: int
    telegram_bot_token: str
    telegram_chat_id: str
    max_upload_bytes: int = 5 * 1024 * 1024


def get_settings() -> Settings:
    host = os.environ.get("TRACKER_HOST", "127.0.0.1").strip() or "127.0.0.1"
    try:
        port = int(os.environ.get("TRACKER_PORT", "8000"))
    except ValueError:
        port = 8000

    raw_db_path = os.environ.get("TRACKER_DB_PATH", "").strip()
    if raw_db_path:
        db_path = Path(raw_db_path)
        if not db_path.is_absolute():
            db_path = (BASE_DIR / db_path).resolve()
    else:
        db_path = (BASE_DIR / "data" / "tracker.db").resolve()

    raw_uploads_dir = os.environ.get("TRACKER_UPLOADS_DIR", "").strip()
    if raw_uploads_dir:
        uploads_dir = Path(raw_uploads_dir)
        if not uploads_dir.is_absolute():
            uploads_dir = (BASE_DIR / uploads_dir).resolve()
    else:
        uploads_dir = (BASE_DIR / "data" / "uploads").resolve()

    enable_scheduler = os.environ.get("TRACKER_ENABLE_SCHEDULER", "1").strip() not in (
        "0",
        "false",
        "False",
        "no",
    )
    try:
        check_interval_minutes = max(
            1, int(os.environ.get("TRACKER_CHECK_INTERVAL_MINUTES", "360"))
        )
    except ValueError:
        check_interval_minutes = 360

    telegram_bot_token = os.environ.get("TRACKER_TELEGRAM_BOT_TOKEN", "").strip()
    telegram_chat_id = os.environ.get("TRACKER_TELEGRAM_CHAT_ID", "").strip()

    db_path.parent.mkdir(parents=True, exist_ok=True)
    uploads_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        host=host,
        port=port,
        db_path=db_path,
        uploads_dir=uploads_dir,
        enable_scheduler=enable_scheduler,
        check_interval_minutes=check_interval_minutes,
        telegram_bot_token=telegram_bot_token,
        telegram_chat_id=telegram_chat_id,
    )
