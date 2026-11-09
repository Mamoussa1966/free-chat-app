from __future__ import annotations

import base64
import json
import time
import uuid

import pytest

from supabase_mfa import SupabaseMFAClient, SupabaseMFAError, session_assurance_level


USER_ID = "d28808d5-699f-479d-92f0-e3518a019028"
FACTOR_ID = "c65a4d8d-44b4-4aff-97e7-b622a2ba275d"
CHALLENGE_ID = "93bbf3bd-41fd-470a-8e38-2856978bbe34"
ISSUER = "https://example.supabase.co/auth/v1"


def _jwt() -> str:
    payload = {
        "sub": USER_ID,
        "role": "authenticated",
        "iss": ISSUER,
        "exp": int(time.time()) + 3600,
        "is_anonymous": False,
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"header.{encoded}.signature"


class _Response:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def _client(session: _Session) -> SupabaseMFAClient:
    return SupabaseMFAClient(
        supabase_url="https://example.supabase.co",
        publishable_key="sb_publishable_abcdefghijklmnopqrstuvwxyz123456",
        access_token=_jwt(),
        verified_user_id=USER_ID,
        expected_issuer=ISSUER,
        session=session,
    )


def test_totp_enrollment_challenge_and_verify_use_fixed_user_auth_routes():
    session = _Session(
        [
            _Response(
                200,
                {
                    "id": USER_ID,
                    "factors": [
                        {
                            "id": FACTOR_ID,
                            "factor_type": "totp",
                            "status": "unverified",
                            "friendly_name": "AI Council Cloudflare Admin",
                            "created_at": "2026-11-09T00:00:00Z",
                        }
                    ],
                },
            ),
            _Response(
                200,
                {
                    "id": FACTOR_ID,
                    "totp": {
                        "qr_code": "<svg></svg>",
                        "secret": "TESTSECRET",
                        "uri": "otpauth://totp/supabase:test",
                    },
                },
            ),
            _Response(200, {"id": CHALLENGE_ID}),
            _Response(200, {"access_token": "new-signed-access-token", "expires_in": 3600}),
        ]
    )
    client = _client(session)

    listed = client.list_factors()
    setup = client.enroll_totp()
    challenge_id = client.challenge(setup["factor_id"])
    verified = client.verify(setup["factor_id"], challenge_id, "123456")

    assert listed["all"][0]["id"] == FACTOR_ID
    assert listed["totp"] == []  # unverified factors are not sign-in-ready
    assert setup["factor_id"] == FACTOR_ID
    assert setup["secret"] == "TESTSECRET"
    assert challenge_id == CHALLENGE_ID
    assert verified["access_token"] == "new-signed-access-token"
    assert [call[0] for call in session.calls] == ["GET", "POST", "POST", "POST"]
    assert [call[1].split("/auth/v1", 1)[1] for call in session.calls] == [
        "/user/",
        "/factors/",
        f"/factors/{FACTOR_ID}/challenge",
        f"/factors/{FACTOR_ID}/verify",
    ]
    assert all(call[2]["allow_redirects"] is False for call in session.calls)
    assert all(call[2]["headers"]["Authorization"] == f"Bearer {_jwt()}" for call in session.calls)
    assert all(call[2]["headers"]["apikey"].startswith("sb_publishable_") for call in session.calls)
    assert session.calls[0][2]["json"] is None  # GET /user
    assert session.calls[1][2]["json"]["factor_type"] == "totp"
    assert session.calls[3][2]["json"] == {"challenge_id": CHALLENGE_ID, "code": "123456"}


@pytest.mark.parametrize("code", ["", "12345", "12x456", "1234567", "12345678", "12345678901", "１２３４５６"])
def test_verify_rejects_invalid_totp_without_http_request(code: str):
    session = _Session([])
    client = _client(session)
    with pytest.raises(ValueError):
        client.verify(FACTOR_ID, CHALLENGE_ID, code)
    assert session.calls == []


@pytest.mark.parametrize("localized_code", ["١٢٣٤٥٦", "۱۲۳۴۵۶"])
def test_verify_normalizes_arabic_and_persian_digits_to_ascii(localized_code: str):
    session = _Session([_Response(200, {"access_token": "new-access-token"})])
    client = _client(session)

    client.verify(FACTOR_ID, CHALLENGE_ID, localized_code)

    assert session.calls[0][2]["json"]["code"] == "123456"


def test_auth_redirect_is_not_followed_or_allowed_to_change_http_method():
    session = _Session([_Response(302, {"location": "/auth/v1/factors/"})])
    client = _client(session)

    with pytest.raises(SupabaseMFAError) as error:
        client.enroll_totp()

    assert error.value.code == "auth_unexpected_redirect"
    assert error.value.status_code == 302
    assert len(session.calls) == 1
    assert session.calls[0][0] == "POST"
    assert session.calls[0][1].endswith("/auth/v1/factors/")
    assert session.calls[0][2]["allow_redirects"] is False


def test_http_error_is_sanitized_and_does_not_retain_raw_body():
    session = _Session([_Response(403, {"code": "mfa_verification_disabled", "message": "do not surface raw"} )])
    client = _client(session)
    with pytest.raises(SupabaseMFAError) as error:
        client.enroll_totp()
    assert error.value.code == "mfa_verification_disabled"
    assert error.value.status_code == 403
    assert "do not surface raw" not in str(error.value)


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "Invalid TOTP code entered"},
        {"error": "Invalid TOTP code entered"},
    ],
)
def test_verify_maps_http_422_to_sanitized_totp_failure_code(payload):
    session = _Session([_Response(422, payload)])
    client = _client(session)

    with pytest.raises(SupabaseMFAError) as error:
        client.verify(FACTOR_ID, CHALLENGE_ID, "123456")

    assert error.value.code == "mfa_verification_failed"
    assert error.value.status_code == 422
    assert "Invalid TOTP code entered" not in str(error.value)


@pytest.mark.parametrize(
    ("aal", "expected"),
    [("aal1", "aal1"), ("aal2", "aal2"), ("unknown-value", "unknown"), (None, "unknown")],
)
def test_session_assurance_level_reports_only_known_aal_claims(aal, expected):
    payload = {
        "sub": USER_ID,
        "role": "authenticated",
        "iss": ISSUER,
        "exp": int(time.time()) + 3600,
        "is_anonymous": False,
    }
    if aal is not None:
        payload["aal"] = aal
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    assert session_assurance_level(f"header.{encoded}.signature") == expected


def test_invalid_factor_id_is_rejected_before_http():
    session = _Session([])
    client = _client(session)
    with pytest.raises(ValueError):
        client.challenge("not-a-uuid")
    assert session.calls == []
