"""Streamlit UI/session boundary for Supabase email-password Auth.

Supabase tokens stay in server-side Streamlit state while connected. When the
browser-persistence key is configured, a custom component stores only an
authenticated, Fernet-encrypted session envelope in browser localStorage so a
new Streamlit connection can restore and revalidate it. Never store tokens in
URLs, logs, chat history, or plaintext browser storage.
"""
from __future__ import annotations

import base64
import hashlib
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
_RECOVERY_STATE_KEY = "_supabase_password_recovery"
_RECOVERY_ACK_KEY = "_supabase_password_recovery_ack"
_RECOVERY_SUCCESS_NOTICE_KEY = "_supabase_recovery_success_notice"
_CLEAR_RECOVERY_WIDGETS_KEY = "_supabase_clear_recovery_widgets"
_RECOVERY_PASSWORD_WIDGET_KEY = "supabase_recovery_new_password"
_RECOVERY_CONFIRM_WIDGET_KEY = "supabase_recovery_confirm_password"

_RECOVERY_PARENT_BRIDGE_ID = "ai-council-supabase-auth-v1"
_RECOVERY_PARENT_BRIDGE_HTML = r"""
<div data-ai-council-supabase-auth-bridge="v1" hidden></div>
<script>
(() => {
  "use strict";
  const bridgeName = "__aiCouncilSupabaseRecoveryBridgeV1";
  const bridgeId = "ai-council-supabase-auth-v1";
  const bridge = window[bridgeName] || (window[bridgeName] = {
    pending: null,
    listenerInstalled: false
  });

  // Supabase's implicit recovery callback places the one-time session in the
  // top-level URL fragment. This script executes in the Streamlit document
  // itself, so it does not attempt to read the fragment from a sandboxed iframe.
  const fragment = String(window.location.hash || "");
  if (fragment && fragment.length <= 16384) {
    const params = new URLSearchParams(fragment.charAt(0) === "#" ? fragment.slice(1) : fragment);
    if (params.get("type") === "recovery") {
      const accessToken = String(params.get("access_token") || "");
      const refreshToken = String(params.get("refresh_token") || "");
      if (accessToken && accessToken.length <= 8192 && refreshToken.length <= 8192) {
        const recoveryId = (window.crypto && crypto.randomUUID)
          ? crypto.randomUUID()
          : String(Date.now()) + "-" + Math.random().toString(36).slice(2);
        bridge.pending = {
          status: "password_recovery",
          recovery_id: recoveryId,
          access_token: accessToken,
          refresh_token: refreshToken,
          token_type: String(params.get("token_type") || "bearer"),
          expires_in: Number(params.get("expires_in") || 1800)
        };
        // Remove one-time credentials before any network/render cycle can log the URL.
        window.history.replaceState(
          window.history.state,
          document.title,
          window.location.pathname + window.location.search
        );
      }
    }
  }

  function isTrustedRecoveryComponentFrame(source, origin) {
    return Array.from(document.querySelectorAll("iframe")).some((frame) => {
      if (frame.contentWindow !== source) return false;
      try {
        const frameUrl = new URL(frame.getAttribute("src") || "", window.location.href);
        const isCouncilFrame = frameUrl.pathname.indexOf(
          "/component/ai_council_supabase_browser_session"
        ) !== -1;
        // Streamlit may serialize a sandboxed component's origin as "null".
        // In that case, trust only this exact iframe WindowProxy and route.
        return isCouncilFrame && (origin === "null" || origin === frameUrl.origin);
      } catch (_error) {
        return false;
      }
    });
  }

  if (!bridge.listenerInstalled) {
    window.addEventListener("message", (event) => {
      if (
        !event.source ||
        event.source === window ||
        !isTrustedRecoveryComponentFrame(event.source, event.origin)
      ) {
        return;
      }
      const message = event.data || {};
      if (message.bridge !== bridgeId) return;

      if (message.type === "AI_COUNCIL_AUTH_BRIDGE_READY" && bridge.pending) {
        // Respond only to the exact registered recovery component iframe.
        // A sandboxed iframe can have an opaque ("null") origin, so use "*"
        // only with the WindowProxy obtained from this trusted source event.
        event.source.postMessage({
          type: "AI_COUNCIL_RECOVERY_PAYLOAD",
          bridge: bridgeId,
          payload: bridge.pending
        }, event.origin === "null" ? "*" : event.origin);
      } else if (
        message.type === "AI_COUNCIL_RECOVERY_ACK" &&
        bridge.pending &&
        message.recovery_id === bridge.pending.recovery_id
      ) {
        // Python has already verified the token with the issuing Supabase project.
        bridge.pending = null;
      }
    });
    bridge.listenerInstalled = true;
  }
})();
</script>
"""

# Publishable key is intentionally public by Supabase design. It is used only
# to validate recovery sessions issued by the isolated test project. No admin
# or service-role credential is embedded in this application.
_TEST_PROJECT_URL = "https://pidcepvwsezdrlhxqksg.supabase.co"
_TEST_PROJECT_PUBLISHABLE_KEY = "sb_publishable_DYeRykN5_v4KIpwfF6uY6A_yj18ggAz"
_TEST_EMAIL_FINGERPRINTS = {
    "A": "f6cfaac879514b2d2f5ace8c2fe076d14c08639d669d40eb2f8cf3af87273d31",
    "B": "6c53ece92c5e1dcbe3785e183b66ee39f96e61f9b10ff8b4ee497baa54ae3e68",
}

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


def _render_top_level_recovery_bridge(st: Any) -> bool:
    """Capture Supabase's recovery fragment from the top-level Streamlit document.

    The custom-component iframe cannot reliably inspect window.parent.location
    because browser origin/sandbox rules may block that access. A static script
    injected with st.html runs in the page itself, strips the one-time fragment,
    and passes the token only to the exact component frame that handshakes back.
    """
    renderer = getattr(st, "html", None)
    if not callable(renderer):
        st.error(
            "تعذّر تشغيل جسر استعادة كلمة المرور: يتطلب هذا الإصدار دعم "
            "st.html مع unsafe_allow_javascript."
        )
        return False
    try:
        renderer(_RECOVERY_PARENT_BRIDGE_HTML, unsafe_allow_javascript=True)
    except Exception:
        st.error(
            "تعذّر تهيئة استقبال رابط الاستعادة داخل صفحة التطبيق. "
            "أعد فتح التطبيق بعد تحديثه ثم اطلب رابط استعادة جديدًا."
        )
        return False
    return True


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
            recovery_ack=str(state.get(_RECOVERY_ACK_KEY) or ""),
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


def _unverified_jwt_issuer(access_token: str) -> str:
    """Read only the JWT issuer to select an allowlisted Auth endpoint.

    This value is not trusted for identity. The selected project's /user endpoint
    must validate the token signature before any recovery action is enabled.
    """
    parts = str(access_token or "").split(".")
    if len(parts) != 3 or len(parts[1]) > 8192:
        raise SupabaseAuthError("رابط استعادة كلمة المرور غير صالح أو منتهي.")
    try:
        encoded = parts[1]
        payload = json.loads(
            base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-8")
        )
    except Exception:
        raise SupabaseAuthError("تعذر قراءة جلسة استعادة كلمة المرور.") from None
    issuer = str(payload.get("iss") or "") if isinstance(payload, dict) else ""
    if not issuer:
        raise SupabaseAuthError("جلسة الاستعادة لا تحتوي على هوية مشروع صالحة.")
    return issuer


def _recovery_account_label(email: str) -> str:
    normalized = str(email or "").strip().casefold()
    fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    for label, expected in _TEST_EMAIL_FINGERPRINTS.items():
        if fingerprint == expected:
            return label
    return ""


def _client_for_recovery_token(st: Any, access_token: str) -> tuple[SupabaseAuthClient, str]:
    """Choose only between production and the allowlisted isolated test project."""
    issuer = _unverified_jwt_issuer(access_token)
    url, key, enabled = get_supabase_config(st)
    production_issuer = f"{url.rstrip('/')}/auth/v1" if url else ""

    if issuer == f"{_TEST_PROJECT_URL}/auth/v1":
        return (
            SupabaseAuthClient(
                supabase_url=_TEST_PROJECT_URL,
                publishable_key=_secret(st, "SUPABASE_TEST_PUBLISHABLE_KEY") or _TEST_PROJECT_PUBLISHABLE_KEY,
            ),
            "test",
        )
    if enabled and url and key and issuer == production_issuer:
        return SupabaseAuthClient(supabase_url=url, publishable_key=key), "production"
    raise SupabaseAuthError("رابط الاستعادة لا يتبع مشروع اختبار أو إنتاج معتمدًا.")


def _capture_password_recovery(st: Any, browser_result: Any) -> bool:
    """Verify a one-time browser recovery callback with the token's own project."""
    state = st.session_state
    if not isinstance(browser_result, dict) or browser_result.get("status") != "password_recovery":
        return False

    recovery_id = str(browser_result.get("recovery_id") or "")
    if recovery_id:
        state[_RECOVERY_ACK_KEY] = recovery_id

    access_token = str(browser_result.get("access_token") or "").strip()
    refresh_token = str(browser_result.get("refresh_token") or "").strip()
    if not access_token or len(access_token) > 8192:
        state[_AUTH_NOTICE_KEY] = "رابط استعادة كلمة المرور غير مكتمل. اطلب رابطًا جديدًا."
        return True

    try:
        client, project_kind = _client_for_recovery_token(st, access_token)
        user = client.get_verified_user(access_token)
    except (ValueError, SupabaseAuthError):
        state[_AUTH_NOTICE_KEY] = (
            "تعذر التحقق من رابط الاستعادة. ربما انتهت صلاحيته أو لا يتبع مشروع Supabase المعتمد. "
            "اطلب رابط استعادة جديدًا."
        )
        return True

    account_label = _recovery_account_label(str(user.get("email") or "")) if project_kind == "test" else ""
    if project_kind == "test" and not account_label:
        state[_AUTH_NOTICE_KEY] = "الحساب الذي وصل منه الرابط ليس أحد حسابَي الاختبار المعتمدين."
        return True

    try:
        expires_in = int(browser_result.get("expires_in") or 1800)
    except (TypeError, ValueError):
        expires_in = 1800
    expires_in = max(60, min(expires_in, 3600))
    state[_RECOVERY_STATE_KEY] = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": int(time.time()) + expires_in,
        "user_id": str(user["id"]),
        "email": str(user.get("email") or ""),
        "issuer": client.issuer,
        "project_kind": project_kind,
        "account_label": account_label,
    }
    return True


def _render_password_recovery(st: Any) -> None:
    """Complete recovery with the user-scoped access token from the email link."""
    state = st.session_state
    recovery = state.get(_RECOVERY_STATE_KEY)
    if state.pop(_CLEAR_RECOVERY_WIDGETS_KEY, False):
        state.pop(_RECOVERY_PASSWORD_WIDGET_KEY, None)
        state.pop(_RECOVERY_CONFIRM_WIDGET_KEY, None)

    st.title("🔑 تعيين كلمة مرور جديدة")
    if not isinstance(recovery, dict):
        st.error("لا توجد جلسة استعادة صالحة.")
        return

    if int(recovery.get("expires_at") or 0) <= int(time.time()):
        state.pop(_RECOVERY_STATE_KEY, None)
        st.error("انتهت صلاحية رابط استعادة كلمة المرور. اطلب رابطًا جديدًا.")
        return

    project_kind = str(recovery.get("project_kind") or "")
    account_label = str(recovery.get("account_label") or "")
    if project_kind == "test":
        st.info(
            f"الحساب التجريبي ({account_label}) — مشروع الاختبار فقط. "
            "بعد الحفظ سنحدّث السر المقابل في GitHub Actions."
        )
    else:
        st.info("سيتم تحديث كلمة مرور حسابك في مشروع الإنتاج بعد التحقق من جلسة الاستعادة.")

    with st.form("supabase_password_recovery_form"):
        new_password = st.text_input(
            "كلمة المرور الجديدة (8 أحرف على الأقل)",
            type="password",
            key=_RECOVERY_PASSWORD_WIDGET_KEY,
        )
        confirm_password = st.text_input(
            "تأكيد كلمة المرور الجديدة",
            type="password",
            key=_RECOVERY_CONFIRM_WIDGET_KEY,
        )
        submitted = st.form_submit_button(
            "حفظ كلمة المرور الجديدة",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        if new_password != confirm_password:
            st.error("كلمتا المرور غير متطابقتين.")
            return
        try:
            if len(new_password) < 8 or len(new_password) > 1024:
                raise ValueError("كلمة المرور يجب أن تكون بين 8 و1024 حرفًا.")
            if project_kind == "test":
                client = SupabaseAuthClient(
                    supabase_url=_TEST_PROJECT_URL,
                    publishable_key=_secret(st, "SUPABASE_TEST_PUBLISHABLE_KEY") or _TEST_PROJECT_PUBLISHABLE_KEY,
                )
            elif project_kind == "production":
                client = _client(st)
            else:
                raise SupabaseAuthError("مشروع الاسترداد غير معتمد.")
            user = client.update_password(str(recovery.get("access_token") or ""), new_password)
        except (ValueError, SupabaseAuthError) as exc:
            st.error(str(exc) if isinstance(exc, SupabaseAuthError) else "كلمة المرور الجديدة غير صالحة.")
            return

        state.pop(_RECOVERY_STATE_KEY, None)
        state[_CLEAR_RECOVERY_WIDGETS_KEY] = True
        if project_kind == "test":
            state[_RECOVERY_SUCCESS_NOTICE_KEY] = (
                f"تم تحديث كلمة مرور حساب الاختبار ({account_label}) بنجاح. "
                f"حدّث الآن GitHub Secret المقابل: SUPABASE_TEST_USER_{account_label}_PASSWORD "
                "بنفس كلمة المرور الجديدة، ثم أعد اختبار Auth وPostgREST."
            )
        else:
            refresh_token = str(recovery.get("refresh_token") or "").strip()
            if refresh_token:
                expires_at = int(time.time()) + 1800
                session = SupabaseAuthSession(
                    access_token=str(recovery.get("access_token") or ""),
                    refresh_token=refresh_token,
                    expires_at=expires_at,
                    user_id=str(user["id"]),
                    email=str(user.get("email") or recovery.get("email") or ""),
                    issuer=client.issuer,
                    verified_at=int(time.time()),
                )
                _activate_session(st, session)
                _schedule_browser_write(st, session.to_state())
                state[_RECOVERY_SUCCESS_NOTICE_KEY] = "تم تحديث كلمة مرور حسابك وتأكيد الجلسة بنجاح."
            else:
                state[_RECOVERY_SUCCESS_NOTICE_KEY] = (
                    "تم تحديث كلمة المرور بنجاح. سجّل الدخول مجددًا بكلمة المرور الجديدة."
                )
        st.rerun()


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
    if not _render_top_level_recovery_bridge(st):
        return False
    browser_result = _render_browser_session_bridge(st)
    success_notice = st.session_state.pop(_RECOVERY_SUCCESS_NOTICE_KEY, "")
    if success_notice:
        st.success(str(success_notice))
    notice = st.session_state.pop(_AUTH_NOTICE_KEY, "")
    if notice:
        st.warning(str(notice))

    if not isinstance(st.session_state.get(_RECOVERY_STATE_KEY), dict):
        recovery_handled = _capture_password_recovery(st, browser_result)
        if recovery_handled and not isinstance(st.session_state.get(_RECOVERY_STATE_KEY), dict):
            callback_notice = st.session_state.pop(_AUTH_NOTICE_KEY, "")
            if callback_notice:
                st.warning(str(callback_notice))
    if isinstance(st.session_state.get(_RECOVERY_STATE_KEY), dict):
        _render_password_recovery(st)
        return False
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

        with st.form("supabase_password_recovery_request"):
            recovery_email = st.text_input(
                "استعادة كلمة المرور — البريد الإلكتروني",
                key="supabase_recovery_request_email",
            )
            recovery_requested = st.form_submit_button(
                "إرسال رابط استعادة كلمة المرور",
                use_container_width=True,
            )
        if recovery_requested:
            recovery_redirect = (
                _secret(st, "SUPABASE_AUTH_RECOVERY_REDIRECT_URL")
                or "https://free-chat-app-qmqyxzh2oe2n3qwcvqvpdh.streamlit.app/"
            )
            try:
                client.send_password_recovery(recovery_email, recovery_redirect)
            except (ValueError, SupabaseAuthError) as exc:
                st.error(
                    str(exc) if isinstance(exc, SupabaseAuthError)
                    else "راجع عنوان البريد الإلكتروني ورابط الاستعادة."
                )
            else:
                st.success(
                    "تم إرسال طلب الاستعادة إن كان البريد مرتبطًا بحساب. "
                    "افتح رسالة Supabase واتبع الرابط لتعيين كلمة مرور جديدة."
                )

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
