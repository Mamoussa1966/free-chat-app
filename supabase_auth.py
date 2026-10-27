"""Supabase Auth REST client for Streamlit sessions.

Only the publishable/legacy anon project key and the current user's access JWT
are used. Never put a service-role or sb_secret key in this module.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import time
from typing import Any
from urllib.parse import urlsplit
import uuid

import requests


class SupabaseAuthError(RuntimeError):
    """Expected, user-safe authentication failure (never contains response bodies)."""


@dataclass(frozen=True)
class SupabaseAuthSession:
    access_token: str
    refresh_token: str
    expires_at: int
    user_id: str
    email: str
    issuer: str
    verified_at: int

    def to_state(self) -> dict[str, Any]:
        # Tokens are runtime session material; callers must keep this only in
        # Streamlit's server-side session state, never in files, logs, or URLs.
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": int(self.expires_at),
            "user_id": self.user_id,
            "email": self.email,
            "issuer": self.issuer,
            "verified_at": int(self.verified_at),
        }


def _validate_project_url(value: str) -> str:
    parsed = urlsplit(str(value or "").strip())
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError("SUPABASE_URL must be an HTTPS project origin")
    return f"https://{parsed.netloc}".rstrip("/")


def _validate_publishable_key(value: str) -> str:
    key = str(value or "").strip()
    if key.startswith("sb_publishable_") and len(key) > len("sb_publishable_"):
        return key
    # Compatibility with existing Supabase projects using the legacy anon key.
    if key.count(".") == 2:
        try:
            import base64
            import json
            encoded = key.split(".")[1]
            claims = json.loads(
                base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-8")
            )
            if claims.get("role") == "anon":
                return key
            if claims.get("role") in {"service_role", "supabase_admin"}:
                raise ValueError("A service-role/admin key is forbidden")
        except ValueError:
            raise
        except Exception:
            pass
    if key.startswith("sb_secret_"):
        raise ValueError("A Supabase secret key is forbidden")
    raise ValueError("SUPABASE_PUBLISHABLE_KEY must be a publishable or legacy anon key")


class SupabaseAuthClient:
    """Small REST client that verifies identity with Auth's /user endpoint."""

    def __init__(
        self,
        *,
        supabase_url: str,
        publishable_key: str,
        timeout_seconds: float = 10.0,
        session: Any | None = None,
    ) -> None:
        self.base_url = _validate_project_url(supabase_url)
        self.publishable_key = _validate_publishable_key(publishable_key)
        self.issuer = f"{self.base_url}/auth/v1"
        try:
            self.timeout = float(timeout_seconds)
        except (TypeError, ValueError):
            raise ValueError("timeout_seconds must be positive") from None
        if not 0 < self.timeout <= 30:
            raise ValueError("timeout_seconds must be between 0 and 30")
        self._session = session if session is not None else requests.Session()

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        access_token: str = "",
    ) -> dict[str, Any]:
        headers = {
            "apikey": self.publishable_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        try:
            response = self._session.request(
                method,
                f"{self.base_url}/auth/v1/{path.lstrip('/')}",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException:
            raise SupabaseAuthError("تعذر الاتصال بخدمة تسجيل الدخول. حاول مرة أخرى.") from None
        except Exception:
            raise SupabaseAuthError("تعذر إكمال طلب تسجيل الدخول.") from None

        status = int(getattr(response, "status_code", 0) or 0)
        if not 200 <= status < 300:
            # Inspect only an allowlisted pattern to give actionable errors.
            # Never return or log raw response data, which can contain user values.
            provider_message = ""
            try:
                error_data = response.json()
                if isinstance(error_data, dict):
                    provider_message = " ".join(
                        str(error_data.get(field) or "")
                        for field in ("msg", "message", "error_description")
                    ).lower()
            except Exception:
                pass

            if (
                "unable to validate email address" in provider_message
                and "invalid format" in provider_message
            ):
                message = (
                    "صيغة البريد الإلكتروني غير صالحة في Supabase؛ "
                    "استخدم عنوانًا حقيقيًا بصيغة name@example.com."
                )
            elif status in (401, 403):
                message = "بيانات الدخول غير صحيحة أو انتهت الجلسة."
            elif status == 429:
                message = "طلبات تسجيل الدخول كثيرة. انتظر قليلًا ثم أعد المحاولة."
            elif status in (400, 422):
                message = "تعذر قبول بيانات المصادقة. راجع البريد الإلكتروني وكلمة المرور."
            elif status == 409:
                message = "تعذر إنشاء الحساب بهذه البيانات."
            else:
                message = f"تعذر إكمال المصادقة (HTTP {status or 'unknown'})."
            raise SupabaseAuthError(message)

        # Supabase Auth sign-out commonly returns HTTP 204 with no JSON body.
        if status == 204:
            return {}

        try:
            data = response.json()
        except Exception:
            raise SupabaseAuthError("أرجعت خدمة المصادقة استجابة غير صالحة.") from None
        if not isinstance(data, dict):
            raise SupabaseAuthError("أرجعت خدمة المصادقة استجابة غير صالحة.")
        return data

    @staticmethod
    def _normalized_email(email: str) -> str:
        value = str(email or "").strip()
        if not value or len(value) > 254 or "\n" in value or "\r" in value:
            raise ValueError(
                "صيغة البريد غير صالحة؛ أدخل عنوانًا كاملًا بصيغة name@domain.com."
            )
        if value.count("@") != 1:
            raise ValueError(
                "صيغة البريد غير صالحة؛ يجب أن يحتوي العنوان على علامة @ واحدة فقط، "
                "ومن دون علامات اقتباس أو مسافات داخلية."
            )
        local, domain = value.rsplit("@", 1)
        local_pattern = r"^[A-Za-z0-9.!#$%&'*+/=?^_{|}~-]+$"
        domain_label_pattern = re.compile(
            r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
        )
        labels = domain.split(".")
        if (
            not local
            or len(local) > 64
            or local.startswith(".")
            or local.endswith(".")
            or ".." in local
            or re.fullmatch(local_pattern, local) is None
        ):
            raise ValueError(
                "الجزء الذي يسبق @ غير صالح؛ أزل علامات الاقتباس والمسافات "
                "واستخدم اسم صندوق بريد صحيحًا."
            )
        if (
            len(labels) < 2
            or any(
                not label
                or len(label) > 63
                or domain_label_pattern.fullmatch(label) is None
                for label in labels
            )
        ):
            raise ValueError(
                "النطاق بعد @ غير صالح؛ استخدم نطاق بريد كاملًا مثل نطاق مزود بريد حقيقي."
            )
        if domain.lower() in {"example.com", "example.net", "example.org"} or labels[-1].lower() in {
            "test", "example", "invalid", "localhost", "local", "internal"
        }:
            raise ValueError(
                "هذا نطاق تجريبي/محجوز لا يستقبل بريد تأكيد؛ استخدم عنوانًا حقيقيًا "
                "تستطيع فتح رسائله."
            )
        return value

    @staticmethod
    def _validate_password(password: str) -> str:
        value = str(password or "")
        if len(value) < 8 or len(value) > 1024:
            raise ValueError("كلمة المرور يجب أن تكون بين 8 و1024 حرفًا.")
        if "\x00" in value:
            raise ValueError("كلمة المرور غير صالحة.")
        return value

    def sign_up(self, email: str, password: str) -> SupabaseAuthSession | None:
        """Register an email/password user.

        Returns a verified session when Supabase issues one immediately. When
        email confirmation is required, returns None and the UI must ask the
        user to confirm their email before signing in.
        """
        email = self._normalized_email(email)
        password = self._validate_password(password)
        data = self._request("POST", "signup", payload={"email": email, "password": password})
        session_data = data.get("session") if isinstance(data.get("session"), dict) else data
        access = str(session_data.get("access_token") or "").strip()
        refresh = str(session_data.get("refresh_token") or "").strip()
        if not access or not refresh:
            return None
        return self._session_from_tokens(session_data, access, refresh)

    def sign_in(self, email: str, password: str) -> SupabaseAuthSession:
        email = self._normalized_email(email)
        password = self._validate_password(password)
        data = self._request(
            "POST",
            "token?grant_type=password",
            payload={"email": email, "password": password},
        )
        access = str(data.get("access_token") or "").strip()
        refresh = str(data.get("refresh_token") or "").strip()
        if not access or not refresh:
            raise SupabaseAuthError("لم تُصدر خدمة المصادقة جلسة صالحة.")
        return self._session_from_tokens(data, access, refresh)

    def sign_out(self, access_token: str) -> None:
        """Revoke the current user's session with Supabase Auth (local scope)."""
        token = str(access_token or "").strip()
        if not token:
            return
        self._request("POST", "logout?scope=local", access_token=token)

    def refresh_session(self, refresh_token: str) -> SupabaseAuthSession:
        token = str(refresh_token or "").strip()
        if not token:
            raise SupabaseAuthError("انتهت الجلسة؛ سجّل الدخول من جديد.")
        data = self._request(
            "POST",
            "token?grant_type=refresh_token",
            payload={"refresh_token": token},
        )
        access = str(data.get("access_token") or "").strip()
        refresh = str(data.get("refresh_token") or "").strip()
        if not access or not refresh:
            raise SupabaseAuthError("تعذر تجديد الجلسة؛ سجّل الدخول من جديد.")
        return self._session_from_tokens(data, access, refresh)

    def get_verified_user(self, access_token: str) -> dict[str, Any]:
        token = str(access_token or "").strip()
        if not token:
            raise SupabaseAuthError("لا توجد جلسة صالحة. سجّل الدخول.")
        user = self._request("GET", "user", access_token=token)
        user_id = str(user.get("id") or "").strip()
        try:
            normalized_id = str(uuid.UUID(user_id))
        except (TypeError, ValueError, AttributeError):
            raise SupabaseAuthError("لم تستطع خدمة المصادقة إثبات هوية المستخدم.") from None
        if normalized_id != user_id.lower():
            raise SupabaseAuthError("لم تستطع خدمة المصادقة إثبات هوية المستخدم.")
        # The ID is accepted only from the authenticated Auth /user response;
        # never derive authorization identity from an email or decoded JWT claim.
        return {**user, "id": normalized_id}

    def _session_from_tokens(
        self, response_data: dict[str, Any], access_token: str, refresh_token: str
    ) -> SupabaseAuthSession:
        user = self.get_verified_user(access_token)
        user_id = str(user["id"])
        try:
            expires_at = int(
                response_data.get("expires_at")
                or (int(time.time()) + int(response_data.get("expires_in") or 3600))
            )
        except (TypeError, ValueError):
            expires_at = int(time.time()) + 3600
        return SupabaseAuthSession(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            user_id=user_id,
            email=str(user.get("email") or ""),
            issuer=self.issuer,
            verified_at=int(time.time()),
        )

    def restore_or_refresh(self, session_state: dict[str, Any]) -> SupabaseAuthSession:
        """Revalidate a stored Streamlit session and rotate tokens near expiry."""
        access = str(session_state.get("access_token") or "").strip()
        refresh = str(session_state.get("refresh_token") or "").strip()
        try:
            expires_at = int(session_state.get("expires_at") or 0)
        except (TypeError, ValueError):
            expires_at = 0
        old_user_id = str(session_state.get("user_id") or "").strip()

        if not access or not refresh or not old_user_id:
            raise SupabaseAuthError("انتهت الجلسة؛ سجّل الدخول من جديد.")
        now = int(time.time())
        if expires_at <= now + 90:
            renewed = self.refresh_session(refresh)
            if renewed.user_id != old_user_id:
                raise SupabaseAuthError("تغيّرت هوية الجلسة؛ سجّل الدخول من جديد.")
            return renewed

        try:
            verified_at = int(session_state.get("verified_at") or 0)
        except (TypeError, ValueError):
            verified_at = 0
        if now - verified_at >= 300:
            # Revalidate periodically, not on every Streamlit keystroke/rerun.
            # The signed access JWT is still verified by Auth/PostgREST on requests.
            user = self.get_verified_user(access)
            if user["id"] != old_user_id:
                raise SupabaseAuthError("لا تتطابق هوية الجلسة مع المستخدم المصادق عليه.")
            return SupabaseAuthSession(
                access_token=access,
                refresh_token=refresh,
                expires_at=expires_at,
                user_id=user["id"],
                email=str(user.get("email") or session_state.get("email") or ""),
                issuer=self.issuer,
                verified_at=now,
            )
        return SupabaseAuthSession(
            access_token=access,
            refresh_token=refresh,
            expires_at=expires_at,
            user_id=old_user_id,
            email=str(session_state.get("email") or ""),
            issuer=self.issuer,
            verified_at=verified_at,
        )
