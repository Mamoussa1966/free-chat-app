from __future__ import annotations

import hashlib

import pytest
import requests

import supabase_auth
from supabase_auth import SupabaseAuthClient, SupabaseAuthError


PROJECT_URL = "https://council-auth-test.supabase.co"
PUBLISHABLE_KEY = "sb_publishable_unit_test_key"
USER_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeee0001"


def _padded_range_body(matching_suffix=None, matching_count=0, *, lines=800):
    rows = []
    if matching_suffix is not None:
        rows.append(f"{matching_suffix}:{matching_count}")
    index = 1
    while len(rows) < lines:
        candidate = f"{index:035X}"
        if candidate != matching_suffix:
            rows.append(f"{candidate}:0")
        index += 1
    return "\r\n".join(rows) + "\r\n"

class FakeAuthResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class FakeAuthTransport:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if method == "PUT" and url.endswith("/auth/v1/user"):
            return FakeAuthResponse(200, "")
        if method == "GET" and url.endswith("/auth/v1/user"):
            class UserResponse:
                status_code = 200
                def json(self):
                    return {"id": USER_ID, "email": "person@gmail.com"}
            return UserResponse()
        return FakeAuthResponse(200, "")


def test_pwned_password_query_sends_only_five_sha1_characters(monkeypatch):
    password = "password"
    digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    calls = []

    def fake_get(url, *, headers, timeout):
        calls.append((url, headers, timeout))
        return FakeAuthResponse(200, _padded_range_body(suffix, 12345))

    monkeypatch.setattr(supabase_auth.requests, "get", fake_get)

    assert supabase_auth._check_pwned_passwords_range(password) is True
    assert len(calls) == 1
    url, headers, timeout = calls[0]
    assert url == f"https://api.pwnedpasswords.com/range/{prefix}"
    assert digest not in url
    assert password not in url.rsplit("/", 1)[-1]
    assert headers["User-Agent"].startswith("AI-Council-Password-Screen/")
    assert headers["Add-Padding"] == "true"
    assert timeout == 5.0


def test_pwned_password_query_ignores_zero_count_padding(monkeypatch):
    password = "unique-test-password-2026"
    digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    response = _padded_range_body(digest[5:], 0)
    monkeypatch.setattr(
        supabase_auth.requests,
        "get",
        lambda *_args, **_kwargs: FakeAuthResponse(200, response),
    )

    assert supabase_auth._check_pwned_passwords_range(password) is False

def test_pwned_password_service_outage_fails_closed(monkeypatch):
    def fail(*_args, **_kwargs):
        raise requests.Timeout("private transport details")

    monkeypatch.setattr(supabase_auth.requests, "get", fail)

    with pytest.raises(SupabaseAuthError, match="لم يتم"):
        supabase_auth._check_pwned_passwords_range("A-Strong-Password-2026")


@pytest.mark.parametrize("status", [403, 429, 500])
def test_pwned_password_non_200_response_fails_closed(monkeypatch, status):
    monkeypatch.setattr(
        supabase_auth.requests,
        "get",
        lambda *_args, **_kwargs: FakeAuthResponse(status, "do not echo provider data"),
    )

    with pytest.raises(SupabaseAuthError, match="لم يتم حفظ"):
        supabase_auth._check_pwned_passwords_range("A-Strong-Password-2026")


def test_signup_rejects_compromised_password_before_supabase_auth_request():
    transport = FakeAuthTransport()
    client = SupabaseAuthClient(
        supabase_url=PROJECT_URL,
        publishable_key=PUBLISHABLE_KEY,
        session=transport,
        password_breach_checker=lambda _password: True,
    )

    with pytest.raises(SupabaseAuthError, match="ظهرت في تسريبات"):
        client.sign_up("person@gmail.com", "A-Strong-Password-2026")

    assert transport.calls == []


def test_password_update_rejects_compromised_password_before_supabase_auth_request():
    transport = FakeAuthTransport()
    client = SupabaseAuthClient(
        supabase_url=PROJECT_URL,
        publishable_key=PUBLISHABLE_KEY,
        session=transport,
        password_breach_checker=lambda _password: True,
    )

    with pytest.raises(SupabaseAuthError, match="ظهرت في تسريبات"):
        client.update_password("recovery-access-token", "A-Strong-Password-2026")

    assert transport.calls == []


def test_password_check_does_not_run_during_signin():
    transport = FakeAuthTransport()
    def must_not_run(_password):
        raise AssertionError("sign-in must not call HIBP")

    class LoginTransport(FakeAuthTransport):
        def request(self, method, url, **kwargs):
            self.calls.append((method, url, kwargs))
            if "token?grant_type=password" in url:
                class TokenResponse:
                    status_code = 200
                    def json(self):
                        return {
                            "access_token": "token-a",
                            "refresh_token": "refresh-a",
                            "expires_in": 3600,
                        }
                return TokenResponse()
            if method == "GET" and url.endswith("/auth/v1/user"):
                class UserResponse:
                    status_code = 200
                    def json(self):
                        return {"id": USER_ID, "email": "person@gmail.com"}
                return UserResponse()
            return super().request(method, url, **kwargs)

    transport = LoginTransport()
    client = SupabaseAuthClient(
        supabase_url=PROJECT_URL,
        publishable_key=PUBLISHABLE_KEY,
        session=transport,
        password_breach_checker=must_not_run,
    )

    session = client.sign_in("person@gmail.com", "A-Strong-Password-2026")
    assert session.user_id == USER_ID



@pytest.mark.parametrize(
    "body",
    [
        "",
        _padded_range_body(lines=799),
        _padded_range_body(lines=1001),
        _padded_range_body().replace(
            _padded_range_body().splitlines()[0],
            "G" * 35 + ":0",
            1,
        ),
        _padded_range_body().replace(
            _padded_range_body().splitlines()[0],
            _padded_range_body().splitlines()[0].split(":")[0] + ":not-a-count",
            1,
        ),
        _padded_range_body().replace(
            _padded_range_body().splitlines()[0],
            "",
            1,
        ),
    ],
)
def test_malformed_or_unexpected_padded_response_fails_closed(monkeypatch, body):
    monkeypatch.setattr(
        supabase_auth.requests,
        "get",
        lambda *_args, **_kwargs: FakeAuthResponse(200, body),
    )

    with pytest.raises(SupabaseAuthError):
        supabase_auth._check_pwned_passwords_range("A-Strong-Password-2026")


def test_duplicate_suffix_in_padded_response_fails_closed(monkeypatch):
    rows = _padded_range_body().splitlines()
    rows[-1] = rows[0]
    monkeypatch.setattr(
        supabase_auth.requests,
        "get",
        lambda *_args, **_kwargs: FakeAuthResponse(200, "\r\n".join(rows)),
    )

    with pytest.raises(SupabaseAuthError, match="مكررة"):
        supabase_auth._check_pwned_passwords_range("A-Strong-Password-2026")


def test_matching_compromised_hash_does_not_skip_later_response_validation(monkeypatch):
    digest = hashlib.sha1(b"password").hexdigest().upper()
    rows = _padded_range_body(digest[5:], 12345).splitlines()
    rows[-1] = "malformed"
    monkeypatch.setattr(
        supabase_auth.requests,
        "get",
        lambda *_args, **_kwargs: FakeAuthResponse(200, "\r\n".join(rows)),
    )

    with pytest.raises(SupabaseAuthError):
        supabase_auth._check_pwned_passwords_range("password")
