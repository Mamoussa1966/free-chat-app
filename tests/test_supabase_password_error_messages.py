from __future__ import annotations

import pytest

from supabase_auth import SupabaseAuthClient, SupabaseAuthError


PROJECT_URL = "https://council-auth-test.supabase.co"
PUBLISHABLE_KEY = "sb_publishable_unit_test_key"
TEST_VALUE = "x" * 20


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class RejectingTransport:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self.payload = payload
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return FakeResponse(self.status_code, self.payload)


def make_client(status_code: int, payload: dict):
    transport = RejectingTransport(status_code, payload)
    client = SupabaseAuthClient(
        supabase_url=PROJECT_URL,
        publishable_key=PUBLISHABLE_KEY,
        session=transport,
        password_breach_checker=lambda _value: False,
    )
    return client, transport


@pytest.mark.parametrize(
    ("status_code", "payload", "expected"),
    [
        (
            422,
            {"code": "weak_password", "message": "provider-only-message"},
            "سياسة قوة كلمة المرور",
        ),
        (
            400,
            {"error": {"code": "password_too_short"}, "message": "provider-only-message"},
            "الحد الأدنى",
        ),
        (
            422,
            {"data": {"error": {"error": "password_too_long"}}, "message": "provider-only-message"},
            "أطول من الحد",
        ),
    ],
)
def test_signup_maps_password_policy_codes_to_actionable_arabic_reason(
    status_code, payload, expected
):
    client, transport = make_client(status_code, payload)

    with pytest.raises(SupabaseAuthError) as caught:
        client.sign_up("person@gmail.com", TEST_VALUE)

    assert expected in str(caught.value)
    assert "provider-only-message" not in str(caught.value)
    assert len(transport.calls) == 1


def test_signup_extracts_minimum_length_from_known_password_message():
    client, _transport = make_client(
        422,
        {"msg": "Password should be at least 12 characters"},
    )

    with pytest.raises(SupabaseAuthError) as caught:
        client.sign_up("person@gmail.com", TEST_VALUE)

    assert "12 أحرف" in str(caught.value)
    assert "at least 12" not in str(caught.value)


def test_signup_unknown_error_does_not_echo_provider_message():
    provider_message = "do not show this provider text"
    client, _transport = make_client(
        422,
        {"code": "unrecognized_code", "message": provider_message},
    )

    with pytest.raises(SupabaseAuthError) as caught:
        client.sign_up("person@gmail.com", TEST_VALUE)

    assert provider_message not in str(caught.value)
    assert "تعذر قبول بيانات المصادقة" in str(caught.value)


def test_password_update_maps_weak_password_code_too():
    client, _transport = make_client(
        422,
        {"code": "weak_password", "message": "provider-only-message"},
    )

    with pytest.raises(SupabaseAuthError, match="سياسة قوة كلمة المرور"):
        client.update_password("recovery-access-token", TEST_VALUE)
