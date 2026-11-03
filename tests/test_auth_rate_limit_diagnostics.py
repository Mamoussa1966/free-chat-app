from __future__ import annotations

import pytest

from supabase_auth import SupabaseAuthClient, SupabaseAuthError


PROJECT_URL = "https://council-auth-test.supabase.co"
PUBLISHABLE_KEY = "sb_publishable_unit_test_key"


class FakeResponse:
    def __init__(self, status_code, payload, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = dict(headers or {})

    def json(self):
        return self._payload


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.response


def make_client(response):
    transport = FakeTransport(response)
    client = SupabaseAuthClient(
        supabase_url=PROJECT_URL,
        publishable_key=PUBLISHABLE_KEY,
        session=transport,
    )
    return client, transport


def test_recovery_rate_limit_names_the_recovery_action_and_wait_duration():
    client, transport = make_client(FakeResponse(
        429,
        {"msg": "For security purposes, you can only request this after 33 seconds."},
    ))

    with pytest.raises(SupabaseAuthError) as caught:
        client.send_password_recovery(
            "a@gmail.com",
            "https://council-auth-test.streamlit.app/",
        )

    message = str(caught.value)
    assert "استعادة كلمة المرور" in message
    assert "33 ثانية" in message
    assert "تسجيل الدخول" not in message
    assert len(transport.calls) == 1


def test_auth_rate_limit_uses_retry_after_header_without_echoing_provider_body():
    provider_secret = "DO_NOT_EXPOSE_THIS_PRIVATE_PROVIDER_TEXT"
    client, _ = make_client(FakeResponse(
        429,
        {"msg": provider_secret},
        headers={"Retry-After": "45"},
    ))

    with pytest.raises(SupabaseAuthError) as caught:
        client._request("POST", "token?grant_type=password", payload={})

    message = str(caught.value)
    assert "طلبات المصادقة" in message
    assert "45 ثانية" in message
    assert provider_secret not in message


@pytest.mark.parametrize("raw_wait", ["0", "-5", "99999", "not-a-number"])
def test_recovery_rate_limit_rejects_unsafe_wait_values(raw_wait):
    client, _ = make_client(FakeResponse(
        429,
        {"msg": f"For security purposes, you can only request this after {raw_wait} seconds."},
    ))

    with pytest.raises(SupabaseAuthError) as caught:
        client.send_password_recovery(
            "a@gmail.com",
            "https://council-auth-test.streamlit.app/",
        )

    assert "استعادة كلمة المرور" in str(caught.value)
    assert "لا تضغط زر إرسال" in str(caught.value)
    assert raw_wait not in str(caught.value)
