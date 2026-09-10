from __future__ import annotations

import base64
import hashlib
import io
import os
import re
import zipfile
from typing import Iterable

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 25 * 1024 * 1024
MAX_FILES = 20
MAX_TEXT_CHARS = 30_000
MAX_ARCHIVE_MEMBERS = 500
MAX_ARCHIVE_UNCOMPRESSED = 20 * 1024 * 1024

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".xml", ".yaml", ".yml",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".kt", ".kts", ".go", ".rs",
    ".c", ".h", ".cpp", ".hpp", ".cs", ".php", ".rb", ".swift", ".sql", ".html",
    ".css", ".scss", ".ini", ".toml", ".log", ".sh", ".bat", ".ps1",
}

IMAGE_MIMES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}


def _safe_name(name: str) -> str:
    raw = os.path.basename(str(name or "attachment").replace("\\", "/"))
    raw = re.sub(r"[\x00-\x1f\x7f]", "_", raw)
    return raw[:240] or "attachment"


def _safe_mime(value: object) -> str:
    mime = str(value or "application/octet-stream").split(";", 1)[0].strip().lower()
    if not re.fullmatch(r"[a-z0-9!#$&^_.+\-]+/[a-z0-9!#$&^_.+\-]+", mime):
        return "application/octet-stream"
    return mime[:120]


def _zip_member_safe(name: str) -> bool:
    normalized = str(name or "").replace("\\", "/")
    if not normalized or normalized.startswith("/") or normalized.startswith("\\"):
        return False
    if re.match(r"^[A-Za-z]:/", normalized):
        return False
    parts = [p for p in normalized.split("/") if p not in ("", ".")]
    return ".." not in parts


def _validate_docx_container(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
            if len(infos) > MAX_ARCHIVE_MEMBERS:
                raise ValueError("DOCX archive contains too many members.")
            total = 0
            for info in infos:
                if not _zip_member_safe(info.filename):
                    raise ValueError("DOCX archive contains an unsafe path.")
                # Unix mode 0120000 denotes a symbolic link.
                if ((info.external_attr >> 16) & 0o170000) == 0o120000:
                    raise ValueError("DOCX archive contains a symbolic link.")
                if info.file_size < 0 or info.file_size > MAX_FILE_BYTES:
                    raise ValueError("DOCX archive member exceeds the safety limit.")
                total += info.file_size
                if total > MAX_ARCHIVE_UNCOMPRESSED:
                    raise ValueError("DOCX archive expands beyond the safety limit.")
            if "word/document.xml" not in zf.namelist():
                raise ValueError("DOCX document.xml is missing.")
    except zipfile.BadZipFile as exc:
        raise ValueError("DOCX archive is invalid.") from exc


def normalize_uploaded_files(files: Iterable[object]) -> list[dict]:
    result: list[dict] = []
    total = 0
    seen: set[bytes] = set()
    for uploaded in files:
        try:
            data = bytes(uploaded.getvalue())
        except Exception as exc:
            raise ValueError("تعذر قراءة أحد المرفقات.") from exc
        if not data:
            continue
        if len(data) > MAX_FILE_BYTES:
            raise ValueError(f"الملف {getattr(uploaded, 'name', 'attachment')} أكبر من الحد المسموح 10 MB.")
        fingerprint = hashlib.sha256(data).digest()
        if fingerprint in seen:
            continue
        if len(result) >= MAX_FILES:
            raise ValueError(f"عدد المرفقات الفريدة يتجاوز الحد المسموح {MAX_FILES} ملفًا.")
        seen.add(fingerprint)
        if total + len(data) > MAX_TOTAL_BYTES:
            raise ValueError("إجمالي المرفقات يتجاوز الحد المسموح 25 MB للرسالة الواحدة.")
        name = _safe_name(getattr(uploaded, "name", "attachment"))
        mime = _safe_mime(getattr(uploaded, "type", None))
        ext = os.path.splitext(name)[1].lower()
        if ext == ".docx":
            try:
                _validate_docx_container(data)
            except ValueError as exc:
                raise ValueError(f"المرفق {name} مرفوض: {exc}") from exc
        result.append({"name": name, "mime": mime, "size": len(data), "data": data, "sha256": hashlib.sha256(data).hexdigest()})
        total += len(data)
    return result


def is_image(att: dict) -> bool:
    mime = str(att.get("mime", "")).lower()
    ext = os.path.splitext(str(att.get("name", "")))[1].lower()
    return mime in IMAGE_MIMES or ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def as_data_url(att: dict) -> str:
    mime = _safe_mime(att.get("mime"))
    return f"data:{mime};base64,{base64.b64encode(bytes(att.get('data', b'') or b'')).decode('ascii')}"


def as_base64(att: dict) -> str:
    return base64.b64encode(bytes(att.get("data", b"") or b"")).decode("ascii")


def extract_text(att: dict) -> str:
    name = str(att.get("name", ""))
    ext = os.path.splitext(name)[1].lower()
    data = bytes(att.get("data", b"") or b"")
    if ext in TEXT_EXTENSIONS or str(att.get("mime", "")).lower().startswith("text/"):
        for encoding in ("utf-8", "utf-8-sig", "cp1256", "latin-1"):
            try:
                return data.decode(encoding)[:MAX_TEXT_CHARS]
            except UnicodeDecodeError:
                continue
    if ext == ".docx":
        try:
            _validate_docx_container(data)
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                xml = zf.read("word/document.xml")[: MAX_TEXT_CHARS * 8].decode("utf-8", "ignore")
            text = re.sub(r"<[^>]+>", " ", xml)
            return re.sub(r"\s+", " ", text).strip()[:MAX_TEXT_CHARS]
        except Exception:
            return ""
    return ""


def attachment_summary(attachments: list[dict], max_chars: int = MAX_TEXT_CHARS) -> str:
    lines = ["ATTACHMENTS:"]
    for att in attachments or []:
        lines.append(f"- {att.get('name')} ({att.get('mime')}, {att.get('size', 0)} bytes)")
        text = extract_text(att)
        if text:
            lines.append(f"  EXTRACTED TEXT:\n{text}")
    return "\n".join(lines)[-max_chars:] if attachments else ""


def public_metadata(attachments: list[dict]) -> list[dict]:
    return [{"name": a.get("name"), "mime": a.get("mime"), "size": a.get("size", 0), "sha256": a.get("sha256", "")} for a in attachments]
