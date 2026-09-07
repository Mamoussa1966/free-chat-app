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

TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".tsv",
    ".json",
    ".xml",
    ".yaml",
    ".yml",
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".java",
    ".kt",
    ".kts",
    ".go",
    ".rs",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".cs",
    ".php",
    ".rb",
    ".swift",
    ".sql",
    ".html",
    ".css",
    ".scss",
    ".ini",
    ".toml",
    ".log",
    ".sh",
    ".bat",
    ".ps1",
}

IMAGE_MIMES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/gif",
}


def _safe_name(name: str) -> str:
    name = os.path.basename(
        name or "attachment"
    )

    name = re.sub(
        r"[\x00-\x1f\x7f]",
        "_",
        name,
    )

    return name[:240]


def normalize_uploaded_files(
    files: Iterable[object],
) -> list[dict]:
    result: list[dict] = []
    total = 0

    seen: set[bytes] = set()

    for uploaded in files:
        if len(result) >= MAX_FILES:
            raise ValueError(
                f"عدد المرفقات يتجاوز الحد "
                f"المسموح {MAX_FILES} ملفًا."
            )

        try:
            data = bytes(
                uploaded.getvalue()
            )
        except Exception:
            raise ValueError(
                "تعذر قراءة أحد المرفقات."
            )

        if not data:
            continue

        if len(data) > MAX_FILE_BYTES:
            raise ValueError(
                f"الملف "
                f"{getattr(uploaded, 'name', 'attachment')} "
                f"أكبر من الحد المسموح 10 MB."
            )

        mime = str(
            getattr(
                uploaded,
                "type",
                None,
            )
            or "application/octet-stream"
        ).strip().lower()

        name = _safe_name(
            str(
                getattr(
                    uploaded,
                    "name",
                    "attachment",
                )
            )
        )

        fingerprint = hashlib.sha256(
            data
        ).digest()

        if fingerprint in seen:
            continue

        seen.add(fingerprint)

        if (
            total + len(data)
            > MAX_TOTAL_BYTES
        ):
            raise ValueError(
                "إجمالي المرفقات يتجاوز "
                "الحد المسموح 25 MB "
                "للرسالة الواحدة."
            )

        result.append(
            {
                "name": name,
                "mime": mime,
                "size": len(data),
                "data": data,
            }
        )

        total += len(data)

    return result


def is_image(
    att: dict,
) -> bool:
    mime = str(
        att.get("mime", "")
    ).lower()

    ext = os.path.splitext(
        att.get("name", "")
    )[1].lower()

    return (
        mime in IMAGE_MIMES
        or ext
        in {
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".gif",
        }
    )


def as_data_url(
    att: dict,
) -> str:
    mime = (
        att.get("mime")
        or "application/octet-stream"
    )

    encoded = base64.b64encode(
        att.get("data", b"")
    ).decode("ascii")

    return (
        f"data:{mime};base64,{encoded}"
    )


def as_base64(
    att: dict,
) -> str:
    return base64.b64encode(
        att.get("data", b"")
    ).decode("ascii")


def extract_text(
    att: dict,
) -> str:
    name = att.get(
        "name",
        "",
    )

    ext = os.path.splitext(
        name
    )[1].lower()

    data = att.get(
        "data",
        b"",
    )

    if (
        ext in TEXT_EXTENSIONS
        or str(
            att.get(
                "mime",
                "",
            )
        ).startswith("text/")
    ):
        for encoding in (
            "utf-8",
            "utf-8-sig",
            "cp1256",
            "latin-1",
        ):
            try:
                return data.decode(
                    encoding
                )[:MAX_TEXT_CHARS]

            except UnicodeDecodeError:
                pass

    if ext == ".docx":
        try:
            with zipfile.ZipFile(
                io.BytesIO(data)
            ) as zf:
                with zf.open(
                    "word/document.xml"
                ) as member:
                    xml = member.read(
                        MAX_TEXT_CHARS * 8
                    ).decode(
                        "utf-8",
                        "ignore",
                    )

            text = re.sub(
                r"<[^>]+>",
                " ",
                xml,
            )

            text = re.sub(
                r"\s+",
                " ",
                text,
            ).strip()

            return text[
                :MAX_TEXT_CHARS
            ]

        except Exception:
            return ""

    return ""


def attachment_summary(
    attachments: list[dict],
    max_chars: int = MAX_TEXT_CHARS,
) -> str:
    if not attachments:
        return ""

    lines = ["ATTACHMENTS:"]

    for att in attachments:
        lines.append(
            f"- {att.get('name')} "
            f"({att.get('mime')}, "
            f"{att.get('size', 0)} bytes)"
        )

        text = extract_text(att)

        if text:
            lines.append(
                "  EXTRACTED TEXT:\n"
                f"{text}"
            )

    return "\n".join(
        lines
    )[-max_chars:]


def public_metadata(
    attachments: list[dict],
) -> list[dict]:
    return [
        {
            "name": a.get("name"),
            "mime": a.get("mime"),
            "size": a.get(
                "size",
                0,
            ),
        }
        for a in attachments
    ]
