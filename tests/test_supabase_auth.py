from __future__ import annotations

import json
import time
import uuid

import pytest

from supabase_auth import SupabaseAuthClient, SupabaseAuthError


PROJECT_URL = "https://council-auth-test.supabase.co"
PUBLISHABLE_KEY = "sb_publishable_unit_test_key"
USER_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeee0001"
ACCESS_A = "access-user-a"
REFRESH_A = "refresh-user-a"
ACCESS_B = "access-user-b"
REFRESH_B = "refresh-user-b"


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeAuthTransport:
    def __init__(self):
        self.calls = []
        self.users = {
            ACCESS_A: {"id": USER_ID, "email": "a@gmail.com"},
            ACCESS_B: {"id": "bbbbbbbb-cccc-4ddd-8eee-ffffffff0002", "email": "b@gmail.com"},
            "new-access": {"id": USER_ID, "email": "a@gmail.com"},
        }

    def request(self, method, url, *, json=None, headers=None, timeout=None):
        self.calls.append({
            "method": method,
            "url": url,
            "json": json,
            "headers": dict(headers or {}),
            "timeout": timeout,
        })
        if url.endswith("/auth/v1/signup"):
            return FakeResponse(200, {
                "user": {"id": "00000000-0000-4000-8000-000000000099"},
                "access_token": ACCESS_A,
                "refresh_token": REFRESH_A,
                "expires_in": 3600,
                "expires_at": int(time.time()) + 3600,
            })
        if "/auth/v1/token?grant_type=password" in url:
            return FakeResponse(200, {
                "access_token": ACCESS_A,
                "refresh_token": REFRESH_A,
                "expires_in": 3600,
                "expires_at": int(time.time()) + 3600,
            })
        if "/auth/v1/token?grant_type=refresh_token" in url:
            return FakeResponse(200, {
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_in": 3600,
                "expires_at": int(time.time()) + 3600,
            })
        if "/auth/v1/logout?scope=local" in url:
            return FakeResponse(204, {})
        if url.endswith("/auth/v1/user"):
            token = (headers or {}).get("Authorization", "").removeprefix("Bearer ")
            user = self.users.get(token)
            if user:
                return FakeResponse(200, user)
            return FakeResponse(401, {"msg": "sensitive response body"})
        return FakeResponse(404, {"msg": "not found"})


def make_client(fake=None):
    transport = fake or FakeAuthTransport()
    return SupabaseAuthClient(
        supabase_url=PROJECT_URL,
        publishable_key=PUBLISHABLE_KEY,
        session=transport,
    ), transport


def test_signup_returns_identity_from_verified_auth_user_response():
    client, transport = make_client()
    session = client.sign_up("a@gmail.com", "Long-Password-123")
    assert session.user_id == USER_ID
    assert session.issuer == PROJECT_URL + "/auth/v1"
    assert session.access_token == ACCESS_A
    signup_call = next(c for c in transport.calls if c["url"].endswith("/auth/v1/signup"))
    assert signup_call["headers"]["apikey"] == PUBLISHABLE_KEY
    assert "Authorization" not in signup_call["headers"]
    # Session identity was read from GET /user, not trusted from signup JSON.
    assert any(c["method"] == "GET" and c["url"].endswith("/auth/v1/user") for c in transport.calls)


@pytest.mark.parametrize("email", [
    "not-an-email",
    "missing-domain@",
    "@example.com",
    "person@example",
    '"person@example.com"',
    "person@@example.com",
    "person name@example.com",
    "person..name@example.com",
    "person@example.test",
    "person@example.com",
    "person@localhost",
])
def test_email_validation_rejects_malformed_addresses_before_network(email):
    client, transport = make_client()
    with pytest.raises(ValueError, match="صيغة البريد|الجزء|النطاق|نطاق تجريبي"):
        client.sign_up(email, "Long-Password-123")
    assert transport.calls == []


def test_supabase_email_format_error_is_mapped_without_echoing_response():
    class InvalidEmailTransport(FakeAuthTransport):
        def request(self, method, url, **kwargs):
            if url.endswith("/auth/v1/signup"):
                return FakeResponse(400, {
                    "msg": "Unable to validate email address: invalid format",
                    "code": "validation_failed",
                })
            return super().request(method, url, **kwargs)

    client, _ = make_client(InvalidEmailTransport())
    with pytest.raises(SupabaseAuthError, match="صيغة البريد الإلكتروني غير صالحة"):
        client.sign_up("a@gmail.com", "Long-Password-123")


def test_signup_without_immediate_session_returns_pending_confirmation():
    class PendingTransport(FakeAuthTransport):
        def request(self, method, url, **kwargs):
            if url.endswith("/auth/v1/signup"):
                return FakeResponse(200, {"user": {"id": USER_ID, "email": "a@gmail.com"}})
            return super().request(method, url, **kwargs)

    client, _ = make_client(PendingTransport())
    assert client.sign_up("a@gmail.com", "Long-Password-123") is None


def test_login_verifies_user_with_auth_endpoint_and_uses_publishable_key():
    client, transport = make_client()
    session = client.sign_in("a@gmail.com", "Long-Password-123")
    assert session.user_id == USER_ID
    login = next(c for c in transport.calls if "grant_type=password" in c["url"])
    assert login["headers"]["apikey"] == PUBLISHABLE_KEY
    assert "service_role" not in repr(login["headers"])
    assert "sb_secret_" not in repr(login["headers"])
    assert login["json"]["password"] == "Long-Password-123"


def test_refresh_rotates_tokens_and_revalidates_the_user():
    client, transport = make_client()
    session = client.refresh_session(REFRESH_A)
    assert session.access_token == "new-access"
    assert session.refresh_token == "new-refresh"
    refresh = next(c for c in transport.calls if "grant_type=refresh_token" in c["url"])
    assert refresh["json"] == {"refresh_token": REFRESH_A}
    user_call = [c for c in transport.calls if c["url"].endswith("/auth/v1/user")][-1]
    assert user_call["headers"]["Authorization"] == "Bearer new-access"


def test_restore_refreshes_near_expiry_and_rejects_subject_change():
    client, _ = make_client()
    session = client.restore_or_refresh({
        "access_token": ACCESS_A,
        "refresh_token": REFRESH_A,
        "expires_at": 1,
        "user_id": USER_ID,
        "email": "a@gmail.com",
        "issuer": PROJECT_URL + "/auth/v1",
    })
    assert session.access_token == "new-access"
    assert session.user_id == USER_ID

    class SwappedRefresh(FakeAuthTransport):
        def request(self, method, url, **kwargs):
            if "grant_type=refresh_token" in url:
                return FakeResponse(200, {
                    "access_token": ACCESS_B,
                    "refresh_token": "refresh-b",
                    "expires_in": 3600,
                    "expires_at": int(time.time()) + 3600,
                })
            return super().request(method, url, **kwargs)

    swapped, _ = make_client(SwappedRefresh())
    with pytest.raises(SupabaseAuthError, match="هوية"):
        swapped.restore_or_refresh({
            "access_token": ACCESS_A,
            "refresh_token": REFRESH_A,
            "expires_at": 1,
            "user_id": USER_ID,
        })


def test_auth_errors_do_not_echo_response_body_or_tokens():
    class BadLogin(FakeAuthTransport):
        def request(self, method, url, **kwargs):
            if "grant_type=password" in url:
                return FakeResponse(401, {
                    "msg": "token=SECRET_VALUE password=PRIVATE_VALUE"
                })
            return super().request(method, url, **kwargs)

    client, _ = make_client(BadLogin())
    with pytest.raises(SupabaseAuthError) as caught:
        client.sign_in("a@gmail.com", "Long-Password-123")
    assert "SECRET_VALUE" not in str(caught.value)
    assert "PRIVATE_VALUE" not in str(caught.value)


@pytest.mark.parametrize("url", [
    "http://council-auth-test.supabase.co",
    "https://user:password@council-auth-test.supabase.co",
    "https://council-auth-test.supabase.co/path",
])
def test_project_url_requires_https_origin(url):
    with pytest.raises(ValueError):
        SupabaseAuthClient(
            supabase_url=url,
            publishable_key=PUBLISHABLE_KEY,
            session=FakeAuthTransport(),
        )


@pytest.mark.parametrize("key", [
    "sb_secret_do_not_use",
    "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.signature",
])
def test_admin_keys_are_rejected(key):
    with pytest.raises(ValueError):
        SupabaseAuthClient(
            supabase_url=PROJECT_URL,
            publishable_key=key,
            session=FakeAuthTransport(),
        )



def test_sign_out_revokes_only_the_current_supabase_session():
    client, transport = make_client()
    client.sign_out(ACCESS_A)
    logout = next(c for c in transport.calls if "/auth/v1/logout?scope=local" in c["url"])
    assert logout["method"] == "POST"
    assert logout["headers"]["Authorization"] == f"Bearer {ACCESS_A}"
    assert logout["headers"]["apikey"] == PUBLISHABLE_KEY
