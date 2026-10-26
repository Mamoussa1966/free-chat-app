"""Streamlit UI/session boundary for Supabase email-password Auth.

Supabase tokens stay in server-side Streamlit state while connected. When the
browser-persistence key is configured, a custom component stores only an
authenticated, Fernet-encrypted session envelope in browser localStorage so a
new Streamlit connection can restore and revalidate it. Never store tokens in
URLs, logs, chat history, or plaintext browser storage.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from streamlit.components.v1 import declare_component

from supabase_auth import SupabaseAuthClient, SupabaseAuthError, SupabaseAuthSession


AUTH_SESSION_KEY = "_supabase_auth_session"
ACTIVE_SUBJECT_KEY = "_supabase_active_subject"
_PENDING_BROWSER_PAYLOAD = "_supabase_pending_browser_payload"
_PENDING_BROWSER_CLEAR = "_supabase_pending_browser_clear"
_PENDING_BROWSER_CLEAR_ID = "_supabase_pending_browser_clear_id"
_AUTH_NOTICE_KEY = "_supabase_auth_notice"
_BROWSER_COMPONENT_KEY = "_supabase_browser_session_bridge"
_BROWSER_STORAGE_KEY = "ai_council_supabase_session_v1"
_BROWSER_SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60

_BROWSER_SESSION_COMPONENT = declare_component(
    "ai_council_supabase_browser_session",
    path=str(Path(__file__).resolve().parent / "supabase_browser_session_component"),
)


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


def _session_fernet(st: Any) -> tuple[Fernet | None, str]:
    """Return (cipher, status); the encryption key must remain server-side."""
    raw = _secret(st, "SUPABASE_SESSION_ENCRYPTION_KEY")
    if not raw:
        return None, "MISSING"
    try:
        return Fernet(raw.encode("ascii")), "READY"
    except (ValueError, TypeError, UnicodeError):
        return None, "INVALID"


def _seal_browser_session_state(st: Any, session_state: dict[str, Any]) -> str:
    """Encrypt a session envelope for browser persistence; never return plaintext."""
    cipher, status = _session_fernet(st)
    if cipher is None or status != "READY":
        return ""
    url, _, _ = get_supabase_config(st)
    if not url:
        return ""
    envelope = {
        "version": 1,
        "saved_at": int(time.time()),
        "issuer": f"{url.rstrip('/')}/auth/v1",
        "session": dict(session_state),
    }
    serialized = json.dumps(envelope, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return cipher.encrypt(serialized.encode("utf-8")).decode("ascii")


def _unseal_browser_session_state(st: Any, token: str) -> dict[str, Any] | None:
    """Decrypt and validate a persisted envelope before asking Auth to revalidate it."""
    cipher, status = _session_fernet(st)
    if cipher is None or status != "READY" or not isinstance(token, str) or not token:
        return None
    if len(token) > 16384:
        return None
    try:
        raw = cipher.decrypt(token.encode("ascii"), ttl=_BROWSER_SESSION_MAX_AGE_SECONDS)
        envelope = json.loads(raw.decode("utf-8"))
    except (InvalidToken, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(envelope, dict) or envelope.get("version") != 1:
        return None
    try:
        saved_at = int(envelope.get("saved_at") or 0)
    except (TypeError, ValueError):
        return None
    now = int(time.time())
    if saved_at <= 0 or saved_at > now + 60 or now - saved_at > _BROWSER_SESSION_MAX_AGE_SECONDS:
        return None

    url, _, enabled = get_supabase_config(st)
    expected_issuer = f"{url.rstrip('/')}/auth/v1" if url else ""
    session_state = envelope.get("session")
    if (
        not enabled
        or envelope.get("issuer") != expected_issuer
        or not isinstance(session_state, dict)
        or not str(session_state.get("access_token") or "").strip()
        or not str(session_state.get("refresh_token") or "").strip()
        or not str(session_state.get("user_id") or "").strip()
        or str(session_state.get("issuer") or "") != expected_issuer
    ):
        return None
    try:
        expires_at = int(session_state.get("expires_at") or 0)
    except (TypeError, ValueError):
        return None
    if expires_at <= 0:
        return None
    return dict(session_state)


def _browser_payload_from_result(value: Any) -> str:
    if isinstance(value, dict) and value.get("status") == "ready":
        payload = value.get("payload")
        return payload if isinstance(payload, str) else ""
    return ""


def _render_browser_session_bridge(st: Any) -> Any:
    """Synchronize pending encrypted persistence/clear operations with the browser."""
    state = st.session_state
    payload = str(state.get(_PENDING_BROWSER_PAYLOAD) or "")
    clear_pending = bool(state.get(_PENDING_BROWSER_CLEAR))
    clear_id = str(state.get(_PENDING_BROWSER_CLEAR_ID) or "")
    try:
        result = _BROWSER_SESSION_COMPONENT(
            persisted_payload=payload,
            clear=clear_pending,
            clear_id=clear_id,
            storage_key=_BROWSER_STORAGE_KEY,
            default=None,
            key=_BROWSER_COMPONENT_KEY,
        )
    except Exception:
        return None

    if payload and _browser_payload_from_result(result) == payload:
        state.pop(_PENDING_BROWSER_PAYLOAD, None)
    if clear_pending and isinstance(result, dict) and result.get("clear_id") == clear_id:
        if result.get("status") in {"empty", "unavailable"}:
            state.pop(_PENDING_BROWSER_CLEAR, None)
            state.pop(_PENDING_BROWSER_CLEAR_ID, None)
    return result


def _schedule_browser_write(st: Any, session_state: dict[str, Any]) -> None:
    sealed = _seal_browser_session_state(st, session_state)
    if sealed:
        st.session_state[_PENDING_BROWSER_PAYLOAD] = sealed


def _schedule_browser_clear(st: Any) -> None:
    st.session_state.pop(_PENDING_BROWSER_PAYLOAD, None)
    st.session_state[_PENDING_BROWSER_CLEAR] = True
    st.session_state[_PENDING_BROWSER_CLEAR_ID] = uuid.uuid4().hex


def is_supabase_auth_active(st: Any) -> bool:
    url, key, enabled = get_supabase_config(st)
    return bool(enabled and url and key and isinstance(st.session_state.get(AUTH_SESSION_KEY), dict))


def _client(st: Any) -> SupabaseAuthClient:
    url, key, enabled = get_supabase_config(st)
    if not (enabled and url and key):
        raise SupabaseAuthError("تسجيل الدخول الدائم غير مفعّل أو إعداداته غير مكتملة.")
    return SupabaseAuthClient(supabase_url=url, publishable_key=key)


def _clear_session_data(state: Any, *, keep_auth: dict[str, Any] | None = None, subject: str = "") -> None:
    # All conversation, context, audit, and widget state is user-scoped. Clear it
    # on account changes and sign-out so one user cannot inherit another session.
    for key in list(state.keys()):
        # Streamlit forbids changing a component widget's state after it has
        # been instantiated in the current run. Keep its opaque browser result;
        # the pending write/clear operation below replaces it on the next run.
        if key == _BROWSER_COMPONENT_KEY:
            continue
        try:
            del state[key]
        except Exception:
            pass
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
    """Revoke the current Supabase session when possible and clear browser state."""
    state = st.session_state
    auth_state = state.get(AUTH_SESSION_KEY)
    logout_failed = False
    if isinstance(auth_state, dict):
        try:
            _client(st).sign_out(str(auth_state.get("access_token") or ""))
        except Exception:
            # Local logout and browser cleanup must still happen even if the
            # Auth endpoint is unavailable; surface the limitation to the user.
            logout_failed = True
    _clear_session_data(state)
    _schedule_browser_clear(st)
    if logout_failed:
        state[_AUTH_NOTICE_KEY] = (
            "تم مسح الجلسة من هذا المتصفح، لكن تعذّر تأكيد إبطالها من خادم Supabase. "
            "تحقّق من الاتصال وسجّل الدخول مجددًا."
        )


def ensure_supabase_auth(st: Any) -> bool | None:
    """Gate the app when enabled; None means Supabase Auth is not configured."""
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

    cipher, cipher_status = _session_fernet(st)
    browser_result = _render_browser_session_bridge(st)
    notice = st.session_state.pop(_AUTH_NOTICE_KEY, "")
    if notice:
        st.warning(str(notice))
    if cipher_status != "READY":
        st.warning(
            "استعادة الدخول عند فتح اتصال جديد غير مفعّلة بعد. أضف سر "
            "SUPABASE_SESSION_ENCRYPTION_KEY (مفتاح Fernet محفوظ في Streamlit Secrets) "
            "لتمكين حفظ الجلسة المشفّر؛ تسجيل الدخول الحالي يظل متاحًا."
        )
    elif isinstance(browser_result, dict) and browser_result.get("status") == "unavailable":
        st.warning(
            "تعذّر الوصول إلى التخزين المحلي للمتصفح؛ سيعمل الدخول للجلسة الحالية فقط "
            "ما لم يسمح المتصفح بتخزين بيانات الموقع."
        )

    stored = st.session_state.get(AUTH_SESSION_KEY)
    recovered_from_browser = False
    if not isinstance(stored, dict) and cipher is not None and cipher_status == "READY":
        browser_payload = _browser_payload_from_result(browser_result)
        if browser_payload:
            recovered = _unseal_browser_session_state(st, browser_payload)
            if recovered is None:
                _schedule_browser_clear(st)
                st.rerun()
                return False
            stored = recovered
            recovered_from_browser = True

    if isinstance(stored, dict):
        try:
            session = client.restore_or_refresh(stored)
        except SupabaseAuthError:
            _clear_session_data(st.session_state)
            _schedule_browser_clear(st)
            st.session_state[_AUTH_NOTICE_KEY] = (
                "انتهت جلسة الدخول أو لم تعد صالحة. تم طلب مسح الجلسة المحفوظة؛ سجّل الدخول مجددًا."
            )
            st.rerun()
            return False
        else:
            refreshed_state = session.to_state()
            needs_browser_update = refreshed_state != stored
            _activate_session(st, session)
            if needs_browser_update and cipher_status == "READY":
                _schedule_browser_write(st, refreshed_state)
                st.rerun()
                return False
            if recovered_from_browser and cipher_status == "READY" and not needs_browser_update:
                # The encrypted browser envelope has already been read and is
                # valid; avoid rewriting it on every rerun.
                pass
            return True

    st.title("🔐 تسجيل الدخول إلى مجلس الذكاء الاصطناعي")
    st.caption("تُحفظ المحادثات تحت حسابك المصادق عليه. لا تستخدم مفاتيح إدارية هنا.")
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
                _schedule_browser_write(st, session.to_state())
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
                        _schedule_browser_write(st, session.to_state())
                        st.rerun()
    st.caption("المصادقة تتم عبر Supabase Auth؛ يتم تأكيد هوية المستخدم من استجابة /auth/v1/user.")
    return False
