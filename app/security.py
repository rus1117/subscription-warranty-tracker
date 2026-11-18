from pathlib import Path
import re
import secrets
from urllib.parse import urlparse
import uuid

from fastapi import HTTPException, UploadFile, status

ALLOWED_EXTENSIONS: dict[str, str] = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

_SAFE_STORED_NAME_RE = re.compile(r"^[0-9a-f]{32}\.(pdf|png|jpg|jpeg|webp)$")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


def validate_cancel_url(url: str | None) -> str | None:
    if url is None:
        return None
    cleaned = url.strip()
    if not cleaned:
        return None
    if len(cleaned) > 500:
        raise ValueError("URL превышает максимальную длину 500 символов")
    if _CONTROL_CHARS_RE.search(cleaned):
        raise ValueError("URL содержит недопустимые управляющие символы")
    parsed = urlparse(cleaned)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError("Разрешены только ссылки с протоколом http:// или https://")
    if not parsed.netloc:
        raise ValueError("В ссылке отсутствует доменное имя")
    return cleaned


def sanitize_display_filename(filename: str | None) -> str:
    if not filename:
        return "receipt"
    raw_name = filename.replace("\\", "/").split("/")[-1]
    cleaned = _CONTROL_CHARS_RE.sub("", raw_name).strip()
    cleaned = cleaned.replace('"', "").replace("'", "")
    if not cleaned or cleaned in (".", ".."):
        return "receipt"
    return cleaned[:200]


def matches_magic_signature(ext: str, data: bytes) -> bool:
    ext_lower = ext.lower()
    if ext_lower == ".pdf":
        return data.startswith(b"%PDF-")
    if ext_lower == ".png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if ext_lower in (".jpg", ".jpeg"):
        return data.startswith(b"\xff\xd8\xff")
    if ext_lower == ".webp":
        return len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    return False


async def validate_and_store_receipt(
    upload: UploadFile,
    uploads_dir: Path,
    max_bytes: int = 5 * 1024 * 1024,
) -> tuple[str, str]:
    original_name = sanitize_display_filename(upload.filename)
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Недопустимый формат файла. Разрешены: PDF, PNG, JPG, JPEG, WEBP.",
        )

    content = await upload.read(max_bytes + 1)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Загружен пустой файл чека.",
        )
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Размер файла превышает допустимый лимит 5 МБ.",
        )

    if not matches_magic_signature(ext, content):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Содержимое файла не соответствует заявленному формату (сигнатура не прошла проверку).",
        )

    uploads_root = uploads_dir.resolve()
    uploads_root.mkdir(parents=True, exist_ok=True)

    stored_name = f"{uuid.uuid4().hex}{ext}"
    target_path = (uploads_root / stored_name).resolve()
    if target_path.parent != uploads_root:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Обнаружена попытка обхода директории сохранения.",
        )

    target_path.write_bytes(content)
    return stored_name, original_name


def resolve_receipt_path(uploads_dir: Path, stored_filename: str | None) -> tuple[Path, str]:
    if not stored_filename:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Файл чека не прикреплен.",
        )
    if (
        "/" in stored_filename
        or "\\" in stored_filename
        or ".." in stored_filename
        or "\x00" in stored_filename
        or not _SAFE_STORED_NAME_RE.match(stored_filename)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Некорректное имя файла чека.",
        )

    uploads_root = uploads_dir.resolve()
    candidate = (uploads_root / stored_filename).resolve()
    if candidate.parent != uploads_root or not candidate.is_relative_to(uploads_root):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Доступ за пределы каталога загрузок запрещен.",
        )
    if not candidate.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Файл чека не найден на диске.",
        )

    ext = candidate.suffix.lower()
    media_type = ALLOWED_EXTENSIONS.get(ext, "application/octet-stream")
    return candidate, media_type


def safe_delete_receipt(uploads_dir: Path, stored_filename: str | None) -> None:
    if not stored_filename or not _SAFE_STORED_NAME_RE.match(stored_filename):
        return
    uploads_root = uploads_dir.resolve()
    candidate = (uploads_root / stored_filename).resolve()
    if candidate.parent == uploads_root and candidate.is_file():
        try:
            candidate.unlink()
        except OSError:
            pass


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)
