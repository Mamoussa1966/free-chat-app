from scripts.test_backup_restore_live import safe_auth_provider_code


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
