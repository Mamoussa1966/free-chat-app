"""Unit/security tests for private Supabase voice-object storage."""
from __future__ import annotations

import base64
import json
from urllib.parse import urlsplit

import pytest

from conversation_repository import AccountIdentity
from supabase_voice_storage import (
    MAX_VOICE_OBJECT_BYTES,
    VOICE_BUCKET,
    SupabaseVoiceStorage,
    VoiceStorageError,
)

PROJECT_URL = "https://council-test.supabase.co"
ISSUER = PROJECT_URL + "/auth/v1"
KEY = "sb_publishable_test_key"
OWNER_A = AccountIdentity(ISSUER, "00000000-0000-0000-0000-00000000000a")
OWNER_B = AccountIdentity(ISSUER, "00000000-0000-0000-0000-00000000000b")


def _b64url(value):
    raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def token_for(owner, role="authenticated"):
    claims = {"role": role, "iss": ISSUER, "sub": owner.subject, "exp": 4102444800}
    return f"{_b64url({'alg': 'none', 'typ': 'JWT'})}.{_b64url(claims)}.test-signature"


class FakeResponse:
    def __init__(self, status_code, content=b""):
        self.status_code = status_code
        self.content = content
        self.text = ""


class FakeStorageSession:
    def __init__(self):
        self.objects = {}
        self.calls = []

    def request(self, method, url, *, headers=None, timeout=None, data=None, json=None):
        self.calls.append({
            "method": method, "url": url, "headers": dict(headers or {}),
            "timeout": timeout, "data": data, "json": json,
        })
        headers = dict(headers or {})
        if headers.get("apikey") != KEY:
            return FakeResponse(401)
        if not headers.get("Authorization", "").startswith("Bearer "):
            return FakeResponse(401)
        path = urlsplit(url).path
        prefix = f"/storage/v1/object/{VOICE_BUCKET}/"
        if method == "POST" and path.startswith(prefix):
            self.objects[path[len(prefix):]] = bytes(data or b"")
            return FakeResponse(200)
        if method == "GET" and path.startswith(prefix):
            stored_path = path[len(prefix):]
            if stored_path not in self.objects:
                return FakeResponse(404)
            return FakeResponse(200, self.objects[stored_path])
        if method == "DELETE" and path == f"/storage/v1/object/{VOICE_BUCKET}":
            for stored_path in (json or {}).get("prefixes", []):
                self.objects.pop(stored_path, None)
            return FakeResponse(200)
        return FakeResponse(404)


def make_storage(owner=OWNER_A, session=None, token=None):
    return SupabaseVoiceStorage(
        supabase_url=PROJECT_URL,
        publishable_key=KEY,
        access_token=token or token_for(owner),
        authenticated_identity=owner,
        session=session or FakeStorageSession(),
    )


def test_upload_download_delete_round_trip_uses_user_jwt_and_private_bucket():
    session = FakeStorageSession()
    storage = make_storage(session=session)
    audio = b"RIFF-test-wav-bytes"
    path = storage.object_path("d0d0013fc3ff485ab56c57e427cbb845", "message_123", "audio/wav")

    storage.upload(path, audio, "audio/wav")
    assert storage.download(path) == audio
    upload = session.calls[0]
    assert upload["method"] == "POST"
    assert upload["headers"]["apikey"] == KEY
    assert upload["headers"]["Authorization"] == f"Bearer {token_for(OWNER_A)}"
    assert upload["headers"]["Content-Type"] == "audio/wav"
    assert "service_role" not in repr(upload["headers"])
    assert "sb_secret_" not in repr(upload["headers"])

    storage.delete([path])
    assert path not in session.objects
    assert session.calls[-1]["method"] == "DELETE"


def test_owner_prefix_is_enforced_before_any_network_request():
    session = FakeStorageSession()
    storage = make_storage(session=session)
    foreign_path = f"{OWNER_B.subject}/conversation-1/message-1.wav"

    with pytest.raises(ValueError, match="belongs to another user"):
        storage.download(foreign_path)
    with pytest.raises(ValueError, match="belongs to another user"):
        storage.delete([foreign_path])
    assert session.calls == []


def test_upload_rejects_empty_oversized_and_unsupported_audio():
    storage = make_storage()
    path = storage.object_path("conversation-1", "message-1", "audio/wav")
    with pytest.raises(ValueError, match="must not be empty"):
        storage.upload(path, b"", "audio/wav")
    with pytest.raises(ValueError, match="8 MiB"):
        storage.upload(path, b"x" * (MAX_VOICE_OBJECT_BYTES + 1), "audio/wav")
    with pytest.raises(ValueError, match="unsupported"):
        storage.object_path("conversation-1", "message-1", "audio/unknown")


def test_storage_failures_do_not_expose_response_bodies():
    class DeniedSession:
        def request(self, *args, **kwargs):
            response = FakeResponse(403)
            response.text = "sensitive internal response body"
            return response

    storage = make_storage(session=DeniedSession())
    path = storage.object_path("conversation-1", "message-1", "audio/wav")
    with pytest.raises(VoiceStorageError) as exc:
        storage.upload(path, b"RIFF-audio", "audio/wav")
    assert "sensitive internal response body" not in str(exc.value)
