from __future__ import annotations

import base64
import json
import time
import uuid

import pytest

from supabase_mfa import SupabaseMFAClient, SupabaseMFAError


USER_ID = "d28808d5-699f-479d-92f0-e3518a019028"
FACTOR_ID = "c65a4d8d-44b4-4aff-97e7-b622a2ba275d"
CHALLENGE_ID = "93bbf3bd-41fd-470a-8e38-2856978bbe34"
ISSUER = "https://example.supabase.co/auth/v1"


def _jwt(aal: str = "aal1") -> str:
    payload = {
        "sub": USER_ID,
        "role": "authenticated",
        "iss": ISSUER,
        "exp": int(time.time()) + 3600,
        "is_anonymous": False,
        "aal": aal,
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


def _client(session: _Session, *, aal: str = "aal1") -> SupabaseMFAClient:
    return SupabaseMFAClient(
        supabase_url="https://example.supabase.co",
        publishable_key="sb_publishable_abcdefghijklmnopqrstuvwxyz123456",
        access_token=_jwt(aal),
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


@pytest.mark.parametrize("code", ["", "12345", "12x456", "1234567", "12345678", "12345678901"])
def test_verify_rejects_invalid_totp_without_http_request(code: str):
    session = _Session([])
    client = _client(session)
    with pytest.raises(ValueError):
        client.verify(FACTOR_ID, CHALLENGE_ID, code)
    assert session.calls == []


def test_current_assurance_level_is_read_from_matching_session_token():
    client = _client(_Session([]), aal="aal2")
    assert client.current_assurance_level == "aal2"
    assert client.assurance_level_for(_jwt("aal1")) == "aal1"


def test_assurance_level_fails_closed_for_wrong_user_or_expired_token():
    client = _client(_Session([]), aal="aal2")
    payload = {
        "sub": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeee0001",
        "role": "authenticated",
        "iss": ISSUER,
        "exp": int(time.time()) + 3600,
        "is_anonymous": False,
        "aal": "aal2",
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    wrong_user = f"header.{encoded}.signature"
    assert client.assurance_level_for(wrong_user) == "aal1"


def test_verify_maps_http_422_to_sanitized_totp_failure_code():
    session = _Session([_Response(422, {"message": "Invalid TOTP code entered"})])
    client = _client(session)
    with pytest.raises(SupabaseMFAError) as error:
        client.verify(FACTOR_ID, CHALLENGE_ID, "123456")
    assert error.value.code == "mfa_verification_failed"
    assert error.value.status_code == 422


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


def test_invalid_factor_id_is_rejected_before_http():
    session = _Session([])
    client = _client(session)
    with pytest.raises(ValueError):
        client.challenge("not-a-uuid")
    assert session.calls == []
