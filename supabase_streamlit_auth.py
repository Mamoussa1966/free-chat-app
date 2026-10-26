"""Streamlit UI/session boundary for Supabase email-password Auth.

Supabase tokens remain server-side during a live Streamlit session. Optional
cross-WebSocket restoration uses an encrypted, host-only browser cookie. The
cookie is ciphertext, not a raw Supabase token. Streamlit's component cookie API
cannot set HttpOnly, so this feature documents that limitation and must not be
described as equivalent to a server-set HttpOnly cookie.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
import time
import uuid
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from supabase_auth import SupabaseAuthClient, SupabaseAuthError, SupabaseAuthSession


AUTH_SESSION_KEY = "_supabase_auth_session"
ACTIVE_SUBJECT_KEY = "_supabase_active_subject"
AUTH_COOKIE_NAME = "__Host-council_auth_v1"
AUTH_COOKIE_MANAGER_STATE_KEY = "_supabase_auth_cookie_manager"
AUTH_COOKIE_PERSISTED_STATE_KEY = "_supabase_auth_cookie_persisted"
AUTH_COOKIE_COMPONENT_KEY = "supabase_auth_cookie_manager"
AUTH_COOKIE_TTL_SECONDS = 30 * 24 * 60 * 60
AUTH_COOKIE_SCHEMA = "supabase-streamlit-auth/v1"
MAX_AUTH_COOKIE_CHARS = 3800


def _secret(st: Any, name: str) -> str:
    value = ""
    try:
        value = str(st.secrets.get(name, "") or "").strip()
    except Exception:
        value = ""
    return value or str(os.environ.get(name, "") or "").strip()


def get_supabase_config(st: Any) -> tuple[str, str, bool]:
    """Return (project URL, publishable key, explicitly_enabled)."""
    url = _secret(st, "SUPABASE_URL")
    key = _secret(st, "SUPABASE_PUBLISHABLE_KEY")
    flag = _secret(st, "SUPABASE_AUTH_ENABLED").lower()
    return url, key, flag in {"1", "true", "yes", "on"}


def is_supabase_auth_active(st: Any) -> bool:
    url, key, enabled = get_supabase_config(st)
    return bool(enabled and url and key and isinstance(st.session_state.get(AUTH_SESSION_KEY), dict))


def _client(st: Any) -> SupabaseAuthClient:
    url, key, enabled = get_supabase_config(st)
    if not (enabled and url and key):
        raise SupabaseAuthError("تسجيل الدخول الدائم غير مفعّل أو إعداداته غير مكتملة.")
    return SupabaseAuthClient(supabase_url=url, publishable_key=key)


def _fernet(st: Any) -> tuple[Fernet | None, str]:
    """Return a Fernet cipher and a non-sensitive configuration status."""
    raw = _secret(st, "SUPABASE_SESSION_ENCRYPTION_KEY")
    if not raw:
        return None, "missing"
    try:
        return Fernet(raw.encode("ascii")), ""
    except (ValueError, TypeError, UnicodeEncodeError):
        return None, "invalid"
    except Exception:
        return None, "invalid"


def _session_state(session: SupabaseAuthSession | dict[str, Any]) -> dict[str, Any]:
    value = session.to_state() if isinstance(session, SupabaseAuthSession) else dict(session)
    required = ("access_token", "refresh_token", "expires_at", "user_id", "email", "issuer", "verified_at")
    if any(not str(value.get(key) or "").strip() for key in required):
        raise ValueError("Supabase session is incomplete.")
    # Never persist arbitrary additional fields or caller-provided metadata.
    return {
        "access_token": str(value["access_token"]),
        "refresh_token": str(value["refresh_token"]),
        "expires_at": int(value["expires_at"]),
        "user_id": str(uuid.UUID(str(value["user_id"]))),
        "email": str(value.get("email") or "")[:254],
        "issuer": str(value["issuer"]),
        "verified_at": int(value["verified_at"]),
    }


def _encode_session_cookie(
    session: SupabaseAuthSession | dict[str, Any],
    fernet: Fernet,
) -> str:
    state = _session_state(session)
    payload = {
        "schema": AUTH_COOKIE_SCHEMA,
        "created_at": int(time.time()),
        "session": state,
    }
    token = fernet.encrypt(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")).decode("ascii")
    if len(token) > MAX_AUTH_COOKIE_CHARS:
        raise ValueError("Encrypted session cookie exceeds the browser cookie size limit.")
    return token


def _decode_session_cookie(
    cookie_value: str,
    fernet: Fernet,
    expected_issuer: str,
) -> dict[str, Any]:
    raw = str(cookie_value or "").strip()
    if not raw or len(raw) > MAX_AUTH_COOKIE_CHARS:
        raise ValueError("Invalid session cookie.")
    try:
        decoded = fernet.decrypt(raw.encode("ascii"), ttl=AUTH_COOKIE_TTL_SECONDS)
        payload = json.loads(decoded.decode("utf-8"))
    except (InvalidToken, ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("Invalid session cookie.") from None
    if not isinstance(payload, dict) or payload.get("schema") != AUTH_COOKIE_SCHEMA:
        raise ValueError("Invalid session cookie schema.")
    state = payload.get("session")
    if not isinstance(state, dict):
        raise ValueError("Invalid session cookie payload.")
    try:
        normalized = _session_state(state)
    except (ValueError, TypeError, KeyError, OverflowError):
        raise ValueError("Invalid session cookie session.") from None
    if normalized["issuer"] != str(expected_issuer):
        raise ValueError("Session issuer does not match the configured Supabase project.")
    if len(normalized["access_token"]) > 8192 or len(normalized["refresh_token"]) > 4096:
        raise ValueError("Invalid session token length.")
    return normalized


def _context_cookie(st: Any) -> str:
    """Read the cookie from the initial HTTP request for this Streamlit session."""
    try:
        cookies = st.context.cookies
        value = cookies.get(AUTH_COOKIE_NAME, "")
        return str(value or "").strip()
    except Exception:
        return ""


def _cookie_manager(st: Any) -> Any | None:
    """Get a per-Streamlit-session component instance; never globally cache cookies."""
    manager = st.session_state.get(AUTH_COOKIE_MANAGER_STATE_KEY)
    if manager is not None:
        return manager
    try:
        import extra_streamlit_components as stx
        manager = stx.CookieManager(key=AUTH_COOKIE_COMPONENT_KEY)
    except Exception:
        return None
    st.session_state[AUTH_COOKIE_MANAGER_STATE_KEY] = manager
    return manager


def _delete_session_cookie(st: Any) -> bool:
    manager = _cookie_manager(st)
    if manager is None:
        return False
    try:
        # CookieManager.delete expects the cookie name to exist in its local dict
        # even when the browser has already removed it; seed only an empty marker.
        local_cookies = getattr(manager, "cookies", None)
        if isinstance(local_cookies, dict):
            local_cookies.setdefault(AUTH_COOKIE_NAME, "")
        manager.delete(AUTH_COOKIE_NAME, key="delete_supabase_auth_session")
        return True
    except Exception:
        return False


def _persist_session_cookie(st: Any, session: SupabaseAuthSession, fernet: Fernet) -> bool:
    manager = _cookie_manager(st)
    if manager is None:
        return False
    try:
        encrypted = _encode_session_cookie(session, fernet)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=AUTH_COOKIE_TTL_SECONDS)
        manager.set(
            AUTH_COOKIE_NAME,
            encrypted,
            key="set_supabase_auth_session",
            path="/",
            expires_at=expires_at,
            max_age=AUTH_COOKIE_TTL_SECONDS,
            secure=True,
            same_site="lax",
        )
        # Avoid reissuing the component command on every Streamlit rerun.
        # A new WebSocket session starts without this in-memory marker and must
        # restore from the browser cookie again.
        st.session_state[AUTH_COOKIE_PERSISTED_STATE_KEY] = True
        return True
    except Exception:
        # Do not log cookie contents, access tokens, or refresh tokens.
        return False


def _clear_session_data(state: Any, *, keep_auth: dict[str, Any] | None = None, subject: str = "") -> None:
    # Conversation, context, audit, and widget data is user-scoped. Preserve only
    # the cookie component handle (infrastructure, not user data) across clearing.
    cookie_manager = state.get(AUTH_COOKIE_MANAGER_STATE_KEY)
    for key in list(state.keys()):
        try:
            del state[key]
        except Exception:
            pass
    if cookie_manager is not None:
        state[AUTH_COOKIE_MANAGER_STATE_KEY] = cookie_manager
    if keep_auth is not None:
        state[AUTH_SESSION_KEY] = keep_auth
    if subject:
        state[ACTIVE_SUBJECT_KEY] = subject


def _activate_session(st: Any, session: SupabaseAuthSession) -> None:
    state = st.session_state
    previous_subject = str(state.get(ACTIVE_SUBJECT_KEY) or "")
    auth_state = session.to_state()
    if previous_subject != session.user_id:
        _clear_session_data(state, keep_auth=auth_state, subject=session.user_id)
    else:
        state[AUTH_SESSION_KEY] = auth_state
        state[ACTIVE_SUBJECT_KEY] = session.user_id


def logout_supabase_user(st: Any) -> None:
    # Remove the persistent browser cookie before clearing in-memory session data.
    _delete_session_cookie(st)
    _clear_session_data(st.session_state)


def ensure_supabase_auth(st: Any) -> bool | None:
    """Gate the app when enabled; None means Supabase Auth is not configured.

    On a new WebSocket session, restore encrypted cookie material, revalidate the
    user with Supabase Auth, and persist any rotated refresh-token pair. Cookie
    restoration is available only when SUPABASE_SESSION_ENCRYPTION_KEY is set.
    """
    url, key, enabled = get_supabase_config(st)
    if not enabled:
        return None
    if not url or not key:
        st.error(
            "تم تفعيل SUPABASE_AUTH_ENABLED لكن SUPABASE_URL أو "
            "SUPABASE_PUBLISHABLE_KEY غير مضبوط في Streamlit Secrets."
        )
        return False

    try:
        client = _client(st)
    except (ValueError, SupabaseAuthError):
        st.error("إعداد Supabase Auth غير صالح. راجع عنوان المشروع ومفتاح Publishable.")
        return False

    fernet, key_status = _fernet(st)
    stored = st.session_state.get(AUTH_SESSION_KEY)
    if isinstance(stored, dict):
        try:
            session = client.restore_or_refresh(stored)
        except SupabaseAuthError:
            _clear_session_data(st.session_state)
            _delete_session_cookie(st)
            st.info("انتهت جلسة الدخول أو لم تعد صالحة. سجّل الدخول مجددًا.")
        else:
            previous_access = str(stored.get("access_token") or "")
            previous_refresh = str(stored.get("refresh_token") or "")
            _activate_session(st, session)
            # Also migrate already-open pre-fix sessions into cookie persistence
            # even when Auth did not need to rotate the tokens this time.
            cookie_missing = not _context_cookie(st)
            cookie_not_written = not bool(st.session_state.get(AUTH_COOKIE_PERSISTED_STATE_KEY))
            if fernet is not None and (
                session.access_token != previous_access
                or session.refresh_token != previous_refresh
                or (cookie_missing and cookie_not_written)
            ):
                if not _persist_session_cookie(st, session, fernet):
                    st.warning("تعذّر تحديث ملف استعادة الجلسة في المتصفح؛ سيظل الدخول الحالي صالحًا مؤقتًا.")
            return True

    cookie_value = _context_cookie(st)
    if cookie_value:
        if fernet is None:
            _delete_session_cookie(st)
            key_message = (
                "استعادة الجلسة بعد إعادة الاتصال غير مفعّلة. أضف "
                "SUPABASE_SESSION_ENCRYPTION_KEY إلى Streamlit Secrets لتفعيلها."
                if key_status == "missing"
                else "مفتاح تشفير استعادة الجلسة غير صالح. صحّحه في Streamlit Secrets ثم سجّل الدخول."
            )
            st.warning(key_message)
        else:
            try:
                cookie_state = _decode_session_cookie(cookie_value, fernet, client.issuer)
                session = client.restore_or_refresh(cookie_state)
            except (ValueError, SupabaseAuthError):
                _delete_session_cookie(st)
                st.info("تعذّر استعادة جلسة المتصفح بأمان. سجّل الدخول مجددًا.")
            else:
                _activate_session(st, session)
                if not _persist_session_cookie(st, session, fernet):
                    st.warning("تم التحقق من الجلسة، لكن تعذّر تجديد ملف الاستعادة في المتصفح.")
                return True

    st.title("🔐 تسجيل الدخول إلى مجلس الذكاء الاصطناعي")
    st.caption("تُحفظ المحادثات تحت حسابك المصادق عليه. لا تستخدم مفاتيح إدارية هنا.")
    if fernet is None:
        key_message = (
            "استعادة الجلسة بعد إعادة تحميل الصفحة تتطلب إضافة "
            "SUPABASE_SESSION_ENCRYPTION_KEY إلى Streamlit Secrets."
            if key_status == "missing"
            else "SUPABASE_SESSION_ENCRYPTION_KEY غير صالح؛ استخدم مفتاح Fernet صحيحًا."
        )
        st.warning(key_message)

    sign_in_tab, sign_up_tab = st.tabs(["تسجيل الدخول", "إنشاء حساب"])

    with sign_in_tab:
        with st.form("supabase_email_password_signin"):
            email = st.text_input("البريد الإلكتروني", key="supabase_signin_email")
            password = st.text_input("كلمة المرور", type="password", key="supabase_signin_password")
            submitted = st.form_submit_button("تسجيل الدخول", type="primary", use_container_width=True)
        if submitted:
            try:
                session = client.sign_in(email, password)
                _activate_session(st, session)
                if fernet is not None and not _persist_session_cookie(st, session, fernet):
                    st.warning("تم تسجيل الدخول، لكن تعذّر حفظ استعادة الجلسة في المتصفح.")
            except (ValueError, SupabaseAuthError) as exc:
                st.error(str(exc) if isinstance(exc, SupabaseAuthError) else "راجع البريد الإلكتروني وكلمة المرور.")
            else:
                st.rerun()

    with sign_up_tab:
        with st.form("supabase_email_password_signup"):
            new_email = st.text_input("البريد الإلكتروني", key="supabase_signup_email")
            new_password = st.text_input("كلمة المرور (8 أحرف على الأقل)", type="password", key="supabase_signup_password")
            confirm_password = st.text_input("تأكيد كلمة المرور", type="password", key="supabase_signup_password_confirm")
            create = st.form_submit_button("إنشاء حساب", type="primary", use_container_width=True)
        if create:
            if new_password != confirm_password:
                st.error("كلمتا المرور غير متطابقتين.")
            else:
                try:
                    session = client.sign_up(new_email, new_password)
                except (ValueError, SupabaseAuthError) as exc:
                    st.error(str(exc) if isinstance(exc, SupabaseAuthError) else "راجع البريد الإلكتروني وكلمة المرور.")
                else:
                    if session is None:
                        st.success("تم استقبال طلب إنشاء الحساب. افتح رسالة التأكيد التي يرسلها Supabase ثم سجّل الدخول.")
                    else:
                        _activate_session(st, session)
                        if fernet is not None and not _persist_session_cookie(st, session, fernet):
                            st.warning("تم إنشاء الجلسة، لكن تعذّر حفظ استعادة الجلسة في المتصفح.")
                        st.rerun()
    st.caption("المصادقة تتم عبر Supabase Auth؛ يتم تأكيد هوية المستخدم من استجابة /auth/v1/user.")
    return False
