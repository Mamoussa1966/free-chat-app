"""Owner-scoped private Supabase Storage for original AI Council voice attachments.

Every request uses the verified user's access JWT and project publishable key.
No service-role/admin key is accepted or required.
"""
from __future__ import annotations

import re
from urllib.parse import quote, urlsplit
from typing import Any

import requests

from conversation_repository import AccountIdentity
from supabase_conversation_repository import (
    _validate_publishable_key,
    _validate_user_access_token,
)

VOICE_BUCKET = "council-voice-files"
MAX_VOICE_OBJECT_BYTES = 8 * 1024 * 1024
_MIME_EXTENSIONS = {
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mpeg": "mp3",
    "audio/mp4": "m4a",
    "audio/aac": "aac",
}
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class VoiceStorageError(RuntimeError):
    """A safe, user-facing storage failure with no response body or secret data."""


class SupabaseVoiceStorage:
    """Minimal REST adapter for per-user private voice blobs."""

    def __init__(
        self,
        *,
        supabase_url: str,
        publishable_key: str,
        access_token: str,
        authenticated_identity: AccountIdentity,
        timeout_seconds: float = 10.0,
        session: Any | None = None,
    ) -> None:
        parsed = urlsplit(str(supabase_url or "").strip())
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
        ):
            raise ValueError("supabase_url must be an HTTPS project origin")
        base_url = f"https://{parsed.netloc}".rstrip("/")
        if not isinstance(authenticated_identity, AccountIdentity):
            raise ValueError("authenticated_identity must be an AccountIdentity")
        if authenticated_identity.issuer != f"{base_url}/auth/v1":
            raise ValueError("identity issuer does not match the configured Supabase project")
        key = _validate_publishable_key(publishable_key)
        if not isinstance(access_token, str) or not access_token.strip():
            raise ValueError("a signed-in user's access token is required")
        _validate_user_access_token(access_token, authenticated_identity)
        try:
            timeout = float(timeout_seconds)
        except (TypeError, ValueError):
            raise ValueError("timeout_seconds must be a positive number") from None
        if timeout <= 0:
            raise ValueError("timeout_seconds must be a positive number")

        self._base_url = base_url
        self._publishable_key = key
        self._access_token = access_token
        self._owner_id = authenticated_identity.subject
        self._timeout = timeout
        self._session = session or requests.Session()

    @staticmethod
    def _segment(value: Any, field: str) -> str:
        segment = str(value or "").strip()
        if not _SAFE_SEGMENT.fullmatch(segment) or segment in {".", ".."}:
            raise ValueError(f"{field} is not a safe storage path segment")
        return segment

    def object_path(self, conversation_id: Any, message_id: Any, mime: str) -> str:
        conversation = self._segment(conversation_id, "conversation_id")
        message = self._segment(message_id, "message_id")
        content_type = str(mime or "audio/wav").split(";", 1)[0].strip().lower()
        extension = _MIME_EXTENSIONS.get(content_type)
        if not extension:
            raise ValueError("unsupported voice attachment MIME type")
        return f"{self._owner_id}/{conversation}/{message}.{extension}"

    def _validate_owned_path(self, path: Any) -> str:
        value = str(path or "").strip()
        parts = value.split("/")
        if (
            len(parts) != 3
            or parts[0] != self._owner_id
            or not _SAFE_SEGMENT.fullmatch(parts[1])
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}\\.(?:wav|webm|ogg|mp3|m4a|aac)", parts[2])
        ):
            raise ValueError("voice attachment path is invalid or belongs to another user")
        return value

    def _request(self, method: str, endpoint: str, *, expected: set[int], **kwargs: Any) -> Any:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.update({
            "apikey": self._publishable_key,
            "Authorization": f"Bearer {self._access_token}",
        })
        try:
            response = self._session.request(
                method,
                f"{self._base_url}{endpoint}",
                headers=headers,
                timeout=self._timeout,
                **kwargs,
            )
        except requests.RequestException:
            raise VoiceStorageError("تعذر الاتصال بتخزين الصوت الخاص في Supabase.") from None
        status = int(getattr(response, "status_code", 0) or 0)
        if status not in expected:
            if status in {401, 403}:
                raise VoiceStorageError("رفض Supabase الوصول إلى ملف الصوت؛ تحقق من جلسة الدخول وسياسات التخزين.")
            if status == 413:
                raise VoiceStorageError("ملف الصوت أكبر من الحد المسموح به.")
            raise VoiceStorageError(f"تعذر إكمال عملية ملف الصوت في Supabase (HTTP {status or 'unknown'}).")
        return response

    def upload(self, path: str, audio_bytes: bytes, mime: str) -> None:
        owned_path = self._validate_owned_path(path)
        if not isinstance(audio_bytes, (bytes, bytearray, memoryview)):
            raise ValueError("audio_bytes must be bytes-like")
        payload = bytes(audio_bytes)
        if not payload:
            raise ValueError("audio attachment must not be empty")
        if len(payload) > MAX_VOICE_OBJECT_BYTES:
            raise ValueError("audio attachment exceeds the configured 8 MiB limit")
        content_type = str(mime or "audio/wav").split(";", 1)[0].strip().lower()
        if content_type not in _MIME_EXTENSIONS:
            raise ValueError("unsupported voice attachment MIME type")
        expected_extension = self.object_path("conversation", "message", content_type).rsplit(".", 1)[-1]
        if not owned_path.endswith(f".{expected_extension}"):
            raise ValueError("voice attachment extension does not match its MIME type")

        self._request(
            "POST",
            f"/storage/v1/object/{VOICE_BUCKET}/{quote(owned_path, safe='/')}",
            expected={200, 201},
            data=payload,
            headers={
                "Content-Type": content_type,
                "x-upsert": "true",
            },
        )

    def download(self, path: str) -> bytes:
        owned_path = self._validate_owned_path(path)
        response = self._request(
            "GET",
            f"/storage/v1/object/{VOICE_BUCKET}/{quote(owned_path, safe='/')}",
            expected={200},
            headers={"Accept": "application/octet-stream"},
        )
        payload = bytes(getattr(response, "content", b"") or b"")
        if not payload:
            raise VoiceStorageError("ملف الصوت المحفوظ فارغ أو غير متاح.")
        if len(payload) > MAX_VOICE_OBJECT_BYTES:
            raise VoiceStorageError("ملف الصوت المحفوظ يتجاوز الحد المسموح.")
        return payload

    def delete(self, paths: list[str]) -> None:
        owned_paths = list(dict.fromkeys(self._validate_owned_path(path) for path in (paths or [])))
        if not owned_paths:
            return
        self._request(
            "DELETE",
            f"/storage/v1/object/{VOICE_BUCKET}",
            expected={200, 204},
            json={"prefixes": owned_paths},
            headers={"Content-Type": "application/json"},
        )
