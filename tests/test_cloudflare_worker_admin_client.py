from __future__ import annotations

import base64
import json
import time

import pytest

from cloudflare_worker_admin_client import (
    CloudflareWorkerAdminClient,
    CloudflareWorkerAdminClientError,
)


PROJECT_URL = "https://council-auth-test.supabase.co"
ISSUER = PROJECT_URL + "/auth/v1"
PUBLISHABLE_KEY = "sb_publishable_unit_test_key"
USER_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeee0001"


def jwt_for(*, role="authenticated", sub=USER_ID, iss=ISSUER, exp=None, is_anonymous=False):
    claims = {
        "role": role,
        "sub": sub,
        "iss": iss,
        "exp": int(exp or time.time() + 3600),
        "is_anonymous": is_anonymous,
    }
    encoded = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return "unit-test-header." + encoded + ".unit-test-signature"


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


class FakeTransport:
    def __init__(self, response=None):
        self.response = response or FakeResponse(200, {
            "ok": True,
            "request_id": "11111111-1111-4111-8111-111111111111",
            "result": [],
        })
        self.calls = []

    def request(self, method, url, *, json=None, headers=None, timeout=None):
        self.calls.append({
            "method": method,
            "url": url,
            "json": json,
            "headers": dict(headers or {}),
            "timeout": timeout,
        })
        return self.response


def make_client(token=None, transport=None, **overrides):
    args = {
        "supabase_url": PROJECT_URL,
        "publishable_key": PUBLISHABLE_KEY,
        "access_token": token or jwt_for(),
        "verified_user_id": USER_ID,
        "expected_issuer": ISSUER,
        "session": transport or FakeTransport(),
    }
    args.update(overrides)
    return CloudflareWorkerAdminClient(**args)


def test_dispatch_uses_user_jwt_and_publishable_key_only():
    transport = FakeTransport()
    client = make_client(transport=transport)

    result = client.dispatch("list", request_id="11111111-1111-4111-8111-111111111111")

    call = transport.calls[0]
    assert result["ok"] is True
    assert call["method"] == "POST"
    assert call["url"] == PROJECT_URL + "/functions/v1/cloudflare-worker-admin"
    assert call["headers"]["apikey"] == PUBLISHABLE_KEY
    assert call["headers"]["Authorization"] == "Bearer " + jwt_for()
    assert call["json"]["operation"] == "list"
    assert call["json"]["worker_name"] is None
    assert call["json"]["request_id"] == "11111111-1111-4111-8111-111111111111"
    assert "service_role" not in json.dumps(call).lower()
    assert "sb_secret_" not in json.dumps(call)


@pytest.mark.parametrize("claims", [
    {"role": "anon"},
    {"role": "service_role"},
    {"role": "authenticated", "is_anonymous": True},
    {"role": "authenticated", "sub": "bbbbbbbb-cccc-4ddd-8eee-ffffffff0002"},
    {"role": "authenticated", "iss": "https://another-project.supabase.co/auth/v1"},
    {"role": "authenticated", "exp": int(time.time()) - 1},
])
def test_rejects_untrusted_or_mismatched_session_claims_before_network(claims):
    transport = FakeTransport()
    token = jwt_for(**claims)
    with pytest.raises(ValueError):
        make_client(token=token, transport=transport)
    assert transport.calls == []


def test_rejects_secret_api_key():
    with pytest.raises(ValueError):
        make_client(publishable_key="sb_secret_do_not_use")


def test_rejects_unsupported_operation_and_invalid_worker_name_before_network():
    transport = FakeTransport()
    client = make_client(transport=transport)

    with pytest.raises(ValueError):
        client.dispatch("raw_http", worker_name="target")
    with pytest.raises(ValueError):
        client.dispatch("delete", worker_name="../other-worker")
    assert transport.calls == []


def test_sanitizes_gateway_error_without_echoing_response_body():
    transport = FakeTransport(FakeResponse(403, {
        "code": "admin_access_denied",
        "message": "must not be exposed",
        "token": "must-not-leak",
    }))
    client = make_client(transport=transport)

    with pytest.raises(CloudflareWorkerAdminClientError) as exc:
        client.dispatch("delete", worker_name="test-worker", confirmation="DELETE test-worker")

    assert exc.value.code == "admin_access_denied"
    assert exc.value.status_code == 403
    assert "must not be exposed" not in str(exc.value)
    assert "must-not-leak" not in str(exc.value)


def test_rejects_oversized_payload_before_network():
    transport = FakeTransport()
    client = make_client(transport=transport)

    with pytest.raises(ValueError, match="size limit"):
        client.dispatch("upload_version", worker_name="simple-worker", payload={"module_js": "x" * 300_000})
    assert transport.calls == []
