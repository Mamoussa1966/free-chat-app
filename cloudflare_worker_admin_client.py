"""Server-side client for the authenticated Cloudflare Worker admin Edge Function.

This client sends a verified user's Supabase JWT and a publishable API key only.
It deliberately has no service-role/secret-key parameter or code path.
"""
from __future__ import annotations

import base64
import json
import re
import time
import uuid
from typing import Any
from urllib.parse import urlsplit

import requests

from supabase_auth import _validate_project_url, _validate_publishable_key


_ALLOWED_OPERATIONS = frozenset(
    {
        "list",
        "register",
        "refresh_versions",
        "update_metadata",
        "upload_version",
        "deploy",
        "rollback",
        "delete",
        "set_policy",
    }
)
_WORKER_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_MAX_REQUEST_BYTES = 300_000


class CloudflareWorkerAdminClientError(RuntimeError):
    """Sanitized admin-gateway error; never stores a raw response or credential."""

    def __init__(self, code: str, status_code: int | None = None) -> None:
        self.code = code if re.fullmatch(r"[a-z0-9_]{1,80}", code or "") else "request_failed"
        self.status_code = status_code
        super().__init__(self.code)


def _jwt_claims_unverified(token: str) -> dict[str, Any]:
    """Local preflight only. Signature verification remains at Supabase Auth/API."""
    parts = token.split(".")
    if len(parts) != 3 or len(parts[1]) > 8192:
        raise ValueError("access_token must be a bounded JWT")
    try:
        raw = base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4))
        value = json.loads(raw.decode("utf-8"))
    except Exception:
        raise ValueError("access_token payload is invalid") from None
    if not isinstance(value, dict):
        raise ValueError("access_token claims must be an object")
    return value


class CloudflareWorkerAdminClient:
    """Calls the JWT-protected Edge Function with the current signed-in user's token."""

    def __init__(
        self,
        *,
        supabase_url: str,
        publishable_key: str,
        access_token: str,
        verified_user_id: str,
        expected_issuer: str,
        timeout_seconds: float = 15.0,
        session: Any | None = None,
    ) -> None:
        self.base_url = _validate_project_url(supabase_url)
        self.publishable_key = _validate_publishable_key(publishable_key)
        self.access_token = str(access_token or "").strip()
        self.verified_user_id = str(verified_user_id or "").strip()
        self.expected_issuer = str(expected_issuer or "").strip()

        parsed_issuer = urlsplit(self.expected_issuer)
        if (
            parsed_issuer.scheme != "https"
            or not parsed_issuer.netloc
            or parsed_issuer.query
            or parsed_issuer.fragment
            or parsed_issuer.path != "/auth/v1"
            or self.expected_issuer != f"{self.base_url}/auth/v1"
        ):
            raise ValueError("expected_issuer must match the configured Supabase project")

        if not self.verified_user_id:
            raise ValueError("verified_user_id is required")
        claims = _jwt_claims_unverified(self.access_token)
        if (
            claims.get("role") != "authenticated"
            or claims.get("sub") != self.verified_user_id
            or claims.get("iss") != self.expected_issuer
            or str(claims.get("is_anonymous", False)).lower() == "true"
            or int(claims.get("exp") or 0) <= int(time.time())
        ):
            raise ValueError("access_token does not match the verified signed-in user session")

        try:
            self.timeout = float(timeout_seconds)
        except (TypeError, ValueError):
            raise ValueError("timeout_seconds must be positive") from None
        if not 0 < self.timeout <= 30:
            raise ValueError("timeout_seconds must be between 0 and 30")

        self._session = session if session is not None else requests.Session()

    def dispatch(
        self,
        operation: str,
        *,
        worker_name: str | None = None,
        payload: dict[str, Any] | None = None,
        confirmation: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Submit one explicitly named operation; database policy is authoritative."""
        if operation not in _ALLOWED_OPERATIONS:
            raise ValueError("Unsupported Cloudflare Worker admin operation")
        if operation == "list":
            if worker_name is not None:
                raise ValueError("list does not accept worker_name")
        elif not isinstance(worker_name, str) or not _WORKER_NAME.fullmatch(worker_name):
            raise ValueError("A valid worker_name is required")

        safe_payload = {} if payload is None else payload
        if not isinstance(safe_payload, dict):
            raise ValueError("payload must be an object")

        correlation_id = str(request_id or uuid.uuid4())
        try:
            uuid.UUID(correlation_id)
        except (TypeError, ValueError, AttributeError):
            raise ValueError("request_id must be a UUID") from None

        body = {
            "operation": operation,
            "worker_name": worker_name,
            "payload": safe_payload,
            "confirmation": confirmation,
            "request_id": correlation_id,
        }
        encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > _MAX_REQUEST_BYTES:
            raise ValueError("request body exceeds the configured size limit")

        headers = {
            "apikey": self.publishable_key,
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        try:
            response = self._session.request(
                "POST",
                f"{self.base_url}/functions/v1/cloudflare-worker-admin",
                json=body,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException:
            raise CloudflareWorkerAdminClientError("gateway_unavailable") from None
        except Exception:
            raise CloudflareWorkerAdminClientError("gateway_request_failed") from None

        status = int(getattr(response, "status_code", 0) or 0)
        try:
            data = response.json()
        except Exception:
            raise CloudflareWorkerAdminClientError("invalid_gateway_response", status) from None

        if not isinstance(data, dict):
            raise CloudflareWorkerAdminClientError("invalid_gateway_response", status)
        if not 200 <= status < 300:
            code = data.get("code")
            raise CloudflareWorkerAdminClientError(
                code if isinstance(code, str) else "gateway_request_rejected",
                status,
            )
        return data
