"""Streamlit UI/session boundary for Supabase email-password Auth.

The feature is fail-safe and opt-in: it activates only when SUPABASE_AUTH_ENABLED
is explicitly true and both project settings exist. The access token stays in
server-side session state; only the refresh token may persist in this browser's
localStorage. Tokens are never written to the repository, logs, or chat history.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import streamlit.components.v1 as components

from supabase_auth import SupabaseAuthClient, SupabaseAuthError, SupabaseAuthSession


AUTH_SESSION_KEY = "_supabase_auth_session"
ACTIVE_SUBJECT_KEY = "_supabase_active_subject"
BROWSER_REFRESH_TOKEN_STORAGE_KEY = "ai-council:supabase-refresh-token:v1"
BROWSER_STORAGE_WIDGET_KEY = "_supabase_browser_auth_storage"
PENDING_BROWSER_TOKEN_KEY = "_supabase_pending_browser_refresh_token"
PENDING_BROWSER_DELETE_KEY = "_supabase_pending_browser_token_delete"
AUTH_RECOVERY_FAILED_KEY = "_supabase_auth_recovery_failed"


@lru_cache(maxsize=1)
def _browser_storage_component():
    """Return a tiny first-party component for browser refresh-token persistence."""
    component_path = Path(__file__).resolve().parent / "components" / "supabase_auth_storage"
    return components.declare_component(
        "ai_council_supabase_refresh_storage_v1",
        path=str(component_path),
    )


def _browser_storage(st: Any, action: str, refresh_token: str = "") -> Any:
    """Read/write/delete only the refresh token using this browser's localStorage."""
    return _browser_storage_component()(
        action=action,
        storage_key=BROWSER_REFRESH_TOKEN_STORAGE_KEY,
        refresh_token=refresh_token,
        key=BROWSER_STORAGE_WIDGET_KEY,
        default=None,
        height=0,
    )


def _normalize_refresh_token(value: Any) -> str | None:
    """Reject malformed values before a token is sent to the configured Auth origin."""
    if not isinstance(value, str) or not value or len(value) > 4096:
        return None
    if value != value.strip() or any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in value):
        return None
    return value


def _browser_storage_response_received(result: Any, expected_action: str) -> bool:
    """Distinguish a reply to the current component action from a stale prior reply."""
    return (
        isinstance(result, dict)
        and result.get("action") == expected_action
        and isinstance(result.get("error"), bool)
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
    _clear_session_data(st.session_state)


def ensure_supabase_auth(st: Any) -> bool | None:
    """Gate the app and restore a persisted browser session through Supabase Auth."""
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

    state = st.session_state
    stored = state.get(AUTH_SESSION_KEY)
    if isinstance(stored, dict):
        old_refresh_token = str(stored.get("refresh_token") or "")
        try:
            session = client.restore_or_refresh(stored)
        except SupabaseAuthError:
            # A stored server-side session is no longer usable. Remove its
            # browser counterpart too; never fall through with the old identity.
            _clear_session_data(state)
            state[AUTH_RECOVERY_FAILED_KEY] = True
            state[PENDING_BROWSER_DELETE_KEY] = True
            st.rerun()
            return False
        else:
            _activate_session(st, session)

            if state.get(PENDING_BROWSER_DELETE_KEY):
                result = _browser_storage(st, "delete")
                if _browser_storage_response_received(result, "delete"):
                    state.pop(PENDING_BROWSER_DELETE_KEY, None)
                    if result.get("error"):
                        state["_supabase_last_storage_error"] = (
                            "تعذّر حذف جلسة الدخول المحفوظة من المتصفح. "
                            "أغلق جلسة التطبيق من هذا المتصفح وتحقق من إعدادات التخزين."
                        )
                    st.rerun()
                st.info("جارٍ إنهاء جلسة الدخول السابقة بأمان…")
                st.stop()

            pending_token = state.get(PENDING_BROWSER_TOKEN_KEY)
            if not pending_token and session.refresh_token != old_refresh_token:
                pending_token = session.refresh_token
                state[PENDING_BROWSER_TOKEN_KEY] = pending_token
            if pending_token:
                result = _browser_storage(st, "write", str(pending_token))
                if _browser_storage_response_received(result, "write"):
                    if result.get("error"):
                        state["_supabase_last_storage_error"] = (
                            "تم الدخول، لكن لم يتمكن المتصفح من حفظ الجلسة. "
                            "قد تحتاج إلى تسجيل الدخول مجددًا بعد تحديث الصفحة."
                        )
                    else:
                        state.pop("_supabase_last_storage_error", None)
                    state.pop(PENDING_BROWSER_TOKEN_KEY, None)
            return True

    # Logout or an invalid saved refresh token must remove the browser copy
    # before another read, otherwise a stale token could be retried forever.
    browser_storage_action_pending = False
    if state.get(PENDING_BROWSER_DELETE_KEY):
        result = _browser_storage(st, "delete")
        if _browser_storage_response_received(result, "delete"):
            state.pop(PENDING_BROWSER_DELETE_KEY, None)
            if result.get("error"):
                state["_supabase_last_storage_error"] = (
                    "تعذّر حذف رمز الجلسة من تخزين المتصفح."
                )
            st.rerun()
        st.info("جارٍ تنظيف جلسة الدخول المحفوظة…")
        # Do not render the same keyed component twice in one Streamlit run.
        # Keep the login form available even if the browser blocks localStorage.
        browser_storage_action_pending = True

    if browser_storage_action_pending:
        browser_result = {"action": "read", "value": "", "error": False}
    else:
        browser_result = _browser_storage(st, "read")
        if not _browser_storage_response_received(browser_result, "read"):
            st.info("جارٍ فحص جلسة الدخول المحفوظة في هذا المتصفح…")
            # The component is still initializing. Showing the login form is a
            # safe fallback; a completed read will trigger a rerun automatically.
            browser_result = {"action": "read", "value": "", "error": False}

    if browser_result.get("error"):
        state[AUTH_RECOVERY_FAILED_KEY] = True
        state[PENDING_BROWSER_DELETE_KEY] = True
        st.rerun()

    refresh_token = _normalize_refresh_token(browser_result.get("value"))
    if refresh_token:
        try:
            session = client.refresh_session(refresh_token)
        except SupabaseAuthError:
            # This refresh token failed at the authoritative Supabase Auth API.
            # Remove it and ask the user to sign in again; never bypass Auth.
            state[AUTH_RECOVERY_FAILED_KEY] = True
            state[PENDING_BROWSER_DELETE_KEY] = True
            st.rerun()
        else:
            _activate_session(st, session)
            state.pop(AUTH_RECOVERY_FAILED_KEY, None)
            state[PENDING_BROWSER_TOKEN_KEY] = session.refresh_token
            st.rerun()

    if state.pop(AUTH_RECOVERY_FAILED_KEY, False):
        st.info("تعذّر استعادة جلسة الدخول المحفوظة. سجّل الدخول مجددًا.")

    st.title("🔐 تسجيل الدخول إلى مجلس الذكاء الاصطناعي")
    st.caption("تُحفظ المحادثات تحت حسابك المصادق عليه. لا تستخدم مفاتيح إدارية هنا.")
    st.caption(
        "لتذكر الدخول بعد تحديث الصفحة، يُحفظ رمز تجديد الجلسة في تخزين هذا المتصفح فقط؛ "
        "لا تُحفظ كلمة المرور، ويُحذف الرمز عند تسجيل الخروج."
    )
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
            except (ValueError, SupabaseAuthError) as exc:
                state.pop(AUTH_RECOVERY_FAILED_KEY, None)
                st.error(str(exc) if isinstance(exc, SupabaseAuthError) else "راجع البريد الإلكتروني وكلمة المرور.")
            else:
                state.pop(AUTH_RECOVERY_FAILED_KEY, None)
                state[PENDING_BROWSER_TOKEN_KEY] = session.refresh_token
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
                        state[PENDING_BROWSER_TOKEN_KEY] = session.refresh_token
                        st.rerun()
    st.caption("المصادقة تتم عبر Supabase Auth؛ يتم تأكيد هوية المستخدم من استجابة /auth/v1/user.")
    return False
