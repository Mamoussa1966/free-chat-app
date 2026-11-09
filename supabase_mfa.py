"""User-scoped Supabase Auth MFA client for TOTP enrollment and step-up.

Only fixed Auth MFA endpoints are exposed. Requests use the current user's
short-lived access JWT and the project's publishable key; no service-role or
Cloudflare credential is accepted or stored here.
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


_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
_SAFE_ERROR_CODE = re.compile(r"^[a-z0-9_]{1,80}$")


class SupabaseMFAError(RuntimeError):
    """Sanitized MFA failure; never retains response bodies or credentials."""

    def __init__(self, code: str, status_code: int | None = None) -> None:
        safe_code = str(code or "")
        self.code = safe_code if _SAFE_ERROR_CODE.fullmatch(safe_code) else "mfa_request_failed"
        self.status_code = int(status_code or 0)
        super().__init__(self.code)


def _jwt_payload(token: str) -> dict[str, Any]:
    parts = str(token or "").split(".")
    if len(parts) != 3 or len(parts[1]) > 8192:
        raise ValueError("access_token must be a bounded JWT")
    try:
        raw = base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4))
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        raise ValueError("access_token payload is invalid") from None
    if not isinstance(payload, dict):
        raise ValueError("access_token claims must be an object")
    return payload


class SupabaseMFAClient:
    """Calls only the fixed Supabase Auth MFA factor endpoints."""

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

        issuer = urlsplit(self.expected_issuer)
        if (
            issuer.scheme != "https"
            or not issuer.netloc
            or issuer.query
            or issuer.fragment
            or issuer.path != "/auth/v1"
            or self.expected_issuer != f"{self.base_url}/auth/v1"
        ):
            raise ValueError("expected_issuer must match the configured Supabase project")
        if not _UUID_RE.fullmatch(self.verified_user_id):
            raise ValueError("verified_user_id must be a UUID")

        claims = _jwt_payload(self.access_token)
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

    @staticmethod
    def _factor_id(value: str) -> str:
        candidate = str(value or "").strip()
        if not _UUID_RE.fullmatch(candidate):
            raise ValueError("factor_id must be a UUID")
        return str(uuid.UUID(candidate))

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict[str, Any]:
        if not path.startswith("/factors") or ".." in path or "://" in path or "#" in path:
            raise ValueError("MFA path is outside the fixed Auth factor API")
        headers = {
            "apikey": self.publishable_key,
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        try:
            response = self._session.request(
                method.upper(),
                f"{self.base_url}/auth/v1{path}",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException:
            raise SupabaseMFAError("auth_unavailable") from None
        except Exception:
            raise SupabaseMFAError("auth_request_failed") from None

        status = int(getattr(response, "status_code", 0) or 0)
        if status == 204:
            return {}
        try:
            data = response.json()
        except Exception:
            raise SupabaseMFAError("invalid_auth_response", status) from None
        if not isinstance(data, dict):
            raise SupabaseMFAError("invalid_auth_response", status)
        if not 200 <= status < 300:
            code = data.get("code") or data.get("error_code") or data.get("error")
            raise SupabaseMFAError(code if isinstance(code, str) else "mfa_request_rejected", status)
        return data

    def list_factors(self) -> dict[str, Any]:
        """Return the current user's Auth MFA factor list."""
        return self._request("GET", "/factors")

    def enroll_totp(self, friendly_name: str = "AI Council Cloudflare Admin") -> dict[str, str]:
        """Create one unverified TOTP factor and return its QR SVG + setup secret."""
        label = str(friendly_name or "").strip()
        if not label or len(label) > 64 or any(ord(char) < 32 for char in label):
            raise ValueError("friendly_name must be 1..64 printable characters")
        data = self._request(
            "POST",
            "/factors",
            {"factor_type": "totp", "friendly_name": label},
        )
        factor_id = self._factor_id(str(data.get("id") or ""))
        totp = data.get("totp")
        if not isinstance(totp, dict):
            raise SupabaseMFAError("totp_setup_data_missing", 200)
        qr_code = str(totp.get("qr_code") or "")
        secret = str(totp.get("secret") or "")
        uri = str(totp.get("uri") or "")
        if not qr_code or not secret or not uri.startswith("otpauth://totp/"):
            raise SupabaseMFAError("totp_setup_data_invalid", 200)
        return {
            "factor_id": factor_id,
            "qr_code": qr_code,
            "secret": secret,
            "uri": uri,
        }

    def challenge(self, factor_id: str) -> str:
        """Create a TOTP challenge for the specified user's factor."""
        factor = self._factor_id(factor_id)
        data = self._request("POST", f"/factors/{factor}/challenge", {})
        challenge_id = self._factor_id(str(data.get("id") or ""))
        return challenge_id

    def verify(self, factor_id: str, challenge_id: str, code: str) -> dict[str, Any]:
        """Verify a TOTP code and return the new AAL2 session response."""
        factor = self._factor_id(factor_id)
        challenge = self._factor_id(challenge_id)
        otp = str(code or "").strip()
        if not re.fullmatch(r"\d{6,10}", otp):
            raise ValueError("TOTP code must contain 6..10 digits")
        data = self._request(
            "POST",
            f"/factors/{factor}/verify",
            {"challenge_id": challenge, "code": otp},
        )
        access_token = str(data.get("access_token") or "").strip()
        if not access_token or len(access_token) > 8192:
            raise SupabaseMFAError("verified_session_missing", 200)
        return data
