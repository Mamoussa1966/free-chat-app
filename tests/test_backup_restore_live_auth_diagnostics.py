from scripts.test_backup_restore_live import required, safe_auth_provider_code


class FakeAuthResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def test_live_auth_diagnostic_keeps_invalid_credentials_code():
    response = FakeAuthResponse({
        "code": "invalid_credentials",
        "message": "sensitive message must never be emitted",
    })
    assert safe_auth_provider_code(response) == "invalid_credentials"


def test_live_auth_diagnostic_rejects_unlisted_provider_text():
    response = FakeAuthResponse({
        "code": "email=private@example.com password=private-value",
        "message": "must never be emitted",
    })
    assert safe_auth_provider_code(response) == "unclassified"


def test_live_auth_diagnostic_handles_malformed_payload_without_echoing_it():
    class BrokenResponse:
        def json(self):
            raise ValueError("body must not escape")

    assert safe_auth_provider_code(BrokenResponse()) == "unclassified"


def test_password_grant_http_400_gets_a_safe_actionable_category():
    response = FakeAuthResponse({
        "message": "Sensitive response text is deliberately ignored",
    })
    assert safe_auth_provider_code(
        response,
        request_url="https://test.supabase.co/auth/v1/token?grant_type=password",
        status=400,
    ) == "password_grant_rejected"


def test_password_grant_fallback_survives_nested_error_payload():
    response = FakeAuthResponse({
        "error": {"code": "invalid_credentials"},
        "message": "Sensitive response text is deliberately ignored",
    })
    assert safe_auth_provider_code(
        response,
        request_url="https://test.supabase.co/auth/v1/token?grant_type=password",
        status=400,
    ) == "password_grant_rejected"



def test_live_restore_password_secret_preserves_leading_and_trailing_whitespace(monkeypatch):
    monkeypatch.setenv("SUPABASE_TEST_USER_A_PASSWORD", "  Existing-Password-Value  ")
    assert required("SUPABASE_TEST_USER_A_PASSWORD", strip=False) == "  Existing-Password-Value  "


def test_live_restore_email_secret_is_trimmed_by_default(monkeypatch):
    monkeypatch.setenv("SUPABASE_TEST_USER_A_EMAIL", "  account-a@example.net  ")
    assert required("SUPABASE_TEST_USER_A_EMAIL") == "account-a@example.net"


def test_live_restore_accepts_identical_passwords_for_distinct_accounts(monkeypatch):
    monkeypatch.setenv("SUPABASE_TEST_USER_A_PASSWORD", "Same-Current-Password")
    monkeypatch.setenv("SUPABASE_TEST_USER_B_PASSWORD", "Same-Current-Password")
    password_a = required("SUPABASE_TEST_USER_A_PASSWORD", strip=False)
    password_b = required("SUPABASE_TEST_USER_B_PASSWORD", strip=False)
    assert password_a == password_b


def test_live_restore_password_secret_rejects_blank_value_without_exposing_it(monkeypatch):
    monkeypatch.setenv("SUPABASE_TEST_USER_A_PASSWORD", "   ")
    try:
        required("SUPABASE_TEST_USER_A_PASSWORD", strip=False)
    except RuntimeError as exc:
        assert "Missing required environment variable" in str(exc)
        assert "   " not in str(exc)
    else:
        raise AssertionError("blank password secret should be rejected")
