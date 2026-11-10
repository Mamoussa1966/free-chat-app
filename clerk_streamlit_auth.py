"""Clerk Development authentication pilot for Streamlit.

This module is deliberately isolated from the production Supabase Auth and
Cloudflare Worker Admin paths. It verifies Clerk session JWTs server-side and
uses only the Clerk user's short-lived token for the isolated Supabase pilot
table. No Clerk Secret Key, Supabase service-role key, or shared JWT secret is
required.
"""
from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlsplit
import uuid

import jwt
import requests
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError
from streamlit.components.v2 import component


TEST_SUPABASE_URL = "https://pidcepvwsezdrlhxqksg.supabase.co"
TEST_CLERK_DOMAIN = "dear-hermit-1240.clerk.accounts.dev"
TEST_CLERK_PUBLISHABLE_KEY = (
    "pk_test_ZGVhci1oZXJtaXQtMTI0MC5jbGVyay5hY2NvdW50cy5kZXYk"
)
DEFAULT_AUTHORIZED_PARTY = (
    "https://free-chat-app-qmqyxzh2oe2n3qwcvqvpdh.streamlit.app"
)
TEST_SUPABASE_PUBLISHABLE_KEY = (
    "sb_publishable_DYeRykN5_v4KIpwfF6uY6A_yj18ggAz"
)

CLERK_SESSION_STATE_KEY = "_clerk_pilot_verified_session"
CLERK_COMPONENT_KEY = "ai_council_clerk_pilot_auth_v1"
MAX_SESSION_TOKEN_LENGTH = 16_384
MAX_RECORD_PAYLOAD_LENGTH = 2_000
_RECORD_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_DOMAIN_RE = re.compile(r"^[a-z0-9-]+\\.clerk\\.accounts\\.dev$")

_JWKS_CLIENTS: dict[str, PyJWKClient] = {}
_JWKS_LOCK = threading.RLock()


class ClerkPilotAuthError(RuntimeError):
    """Safe, user-facing Clerk pilot authentication or configuration error."""


class ClerkPilotAPIError(RuntimeError):
    """Sanitized error from the isolated Supabase PostgREST test endpoint."""


@dataclass(frozen=True)
class ClerkPilotConfig:
    publishable_key: str
    domain: str
    issuer: str
    authorized_parties: tuple[str, ...]
    supabase_url: str
    supabase_publishable_key: str


@dataclass(frozen=True)
class VerifiedClerkSession:
    subject: str
    session_id: str
    issuer: str
    authorized_party: str
    expires_at: int
    issued_at: int
    claims: dict[str, Any]
    access_token: str


def _read_setting(st: Any, name: str, default: str = "") -> str:
    value = ""
    try:
        value = str(st.secrets.get(name, "") or "").strip()
    except Exception:
        pass
    if not value:
        value = str(os.environ.get(name, "") or "").strip()
    return value or default


def _decode_publishable_domain(publishable_key: str) -> str:
    parts = str(publishable_key or "").split("_", 2)
    if len(parts) != 3 or parts[0] != "pk" or parts[1] != "test":
        raise ClerkPilotAuthError(
            "مفتاح Clerk يجب أن يكون Publishable Key تجريبيًا يبدأ بـ pk_test_."
        )
    encoded = parts[2]
    if not encoded or len(encoded) > 2048:
        raise ClerkPilotAuthError("مفتاح Clerk التجريبي غير صالح.")
    try:
        decoded = base64.urlsafe_b64decode(
            encoded + "=" * (-len(encoded) % 4)
        ).decode("utf-8")
    except Exception:
        raise ClerkPilotAuthError("تعذر قراءة نطاق Frontend API من مفتاح Clerk.") from None
    if not decoded.endswith("$"):
        raise ClerkPilotAuthError("صيغة نطاق Clerk داخل Publishable Key غير صالحة.")
    domain = decoded[:-1].lower()
    if not _DOMAIN_RE.fullmatch(domain):
        raise ClerkPilotAuthError("هذه التجربة تقبل نطاق Clerk Development فقط.")
    return domain


def _normalize_origin(value: str) -> str:
    parsed = urlsplit(str(value or "").strip())
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ClerkPilotAuthError(
            "قائمة Clerk المسموح بها يجب أن تحتوي على Origins من HTTPS فقط."
        )
    return f"https://{parsed.netloc}".lower()


def get_clerk_pilot_config(st: Any) -> ClerkPilotConfig:
    """Load only the isolated Clerk Development and Supabase test settings."""
    publishable_key = _read_setting(
        st, "CLERK_TEST_PUBLISHABLE_KEY", TEST_CLERK_PUBLISHABLE_KEY
    )
    configured_domain = _read_setting(
        st, "CLERK_TEST_DOMAIN", TEST_CLERK_DOMAIN
    ).lower()
    decoded_domain = _decode_publishable_domain(publishable_key)
    if not _DOMAIN_RE.fullmatch(configured_domain):
        raise ClerkPilotAuthError("CLERK_TEST_DOMAIN ليس نطاق Clerk Development صالحًا.")
    if decoded_domain != configured_domain or configured_domain != TEST_CLERK_DOMAIN:
        raise ClerkPilotAuthError(
            "نطاق Clerk لا يطابق تطبيق AI Council Test المعتمد لهذه التجربة."
        )

    parties_raw = _read_setting(
        st, "CLERK_TEST_AUTHORIZED_PARTIES", DEFAULT_AUTHORIZED_PARTY
    )
    parties = tuple(
        dict.fromkeys(
            _normalize_origin(item)
            for item in parties_raw.split(",")
            if item.strip()
        )
    )
    if not parties:
        raise ClerkPilotAuthError("لم يتم ضبط Authorized Party مسموح به لتطبيق الاختبار.")

    return ClerkPilotConfig(
        publishable_key=publishable_key,
        domain=configured_domain,
        issuer=f"https://{configured_domain}",
        authorized_parties=parties,
        supabase_url=TEST_SUPABASE_URL,
        supabase_publishable_key=_read_setting(
            st, "SUPABASE_TEST_PUBLISHABLE_KEY", TEST_SUPABASE_PUBLISHABLE_KEY
        ),
    )


def _jwks_client(issuer: str) -> PyJWKClient:
    with _JWKS_LOCK:
        client = _JWKS_CLIENTS.get(issuer)
        if client is None:
            client = PyJWKClient(
                f"{issuer}/.well-known/jwks.json",
                cache_jwk_set=True,
                lifespan=300,
                timeout=5,
            )
            _JWKS_CLIENTS[issuer] = client
        return client


def verify_clerk_session_token(
    token: str,
    *,
    issuer: str,
    authorized_parties: tuple[str, ...] | list[str],
    jwks_client: Any | None = None,
    leeway_seconds: int = 15,
    now: int | None = None,
) -> VerifiedClerkSession:
    """Verify an RS256 Clerk session JWT signature and all authorization claims.

    The token is never decoded and trusted without signature verification.
    The issuer is fixed by server configuration, not read from the token.
    """
    if not isinstance(token, str) or not token or len(token) > MAX_SESSION_TOKEN_LENGTH:
        raise ClerkPilotAuthError("جلسة Clerk غير موجودة أو تجاوزت الحجم المسموح.")
    if not isinstance(issuer, str) or issuer != f"https://{TEST_CLERK_DOMAIN}":
        raise ClerkPilotAuthError("مُصدر Clerk غير معتمد في بيئة الاختبار.")
    parties = tuple(_normalize_origin(x) for x in authorized_parties)
    if not parties:
        raise ClerkPilotAuthError("لا توجد واجهة تطبيق معتمدة لهذه الجلسة.")

    try:
        header = jwt.get_unverified_header(token)
    except InvalidTokenError:
        raise ClerkPilotAuthError("رمز جلسة Clerk ليس JWT صالحًا.") from None
    if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
        raise ClerkPilotAuthError("خوارزمية أو مفتاح توقيع Clerk غير مقبول.")

    client = jwks_client or _jwks_client(issuer)
    try:
        signing_key = client.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            issuer=issuer,
            options={
                "require": ["exp", "iat", "nbf", "iss", "sub", "sid", "azp", "role"],
                "verify_aud": False,
            },
            leeway=max(0, min(int(leeway_seconds), 30)),
        )
    except (InvalidTokenError, PyJWKClientError, requests.RequestException, ValueError):
        raise ClerkPilotAuthError(
            "تعذر التحقق من توقيع جلسة Clerk أو صلاحيتها أو مُصدرها."
        ) from None
    except Exception:
        raise ClerkPilotAuthError(
            "خدمة مفاتيح التوقيع لدى Clerk غير متاحة حاليًا؛ تم رفض الجلسة احترازيًا."
        ) from None

    subject = claims.get("sub")
    session_id = claims.get("sid")
    authorized_party = claims.get("azp")
    if not isinstance(subject, str) or not subject.startswith("user_") or len(subject) > 255:
        raise ClerkPilotAuthError("جلسة Clerk لا تحتوي على User ID صالح.")
    if not isinstance(session_id, str) or not session_id.startswith("sess_"):
        raise ClerkPilotAuthError("جلسة Clerk لا تحتوي على Session ID صالح.")
    if claims.get("role") != "authenticated":
        raise ClerkPilotAuthError(
            "رمز Clerk لا يحمل دور authenticated المطلوب لتكامل Supabase."
        )
    if not isinstance(authorized_party, str) or _normalize_origin(authorized_party) not in parties:
        raise ClerkPilotAuthError(
            "هذا النطاق غير مدرج ضمن Authorized Parties المسموح بها لتطبيق الاختبار."
        )

    issued_at = int(claims["iat"])
    expires_at = int(claims["exp"])
    current = int(time.time()) if now is None else int(now)
    if issued_at > current + 30 or expires_at <= current:
        raise ClerkPilotAuthError("انتهت صلاحية جلسة Clerk أو أن وقت إصدارها غير صالح.")

    return VerifiedClerkSession(
        subject=subject,
        session_id=session_id,
        issuer=issuer,
        authorized_party=authorized_party,
        expires_at=expires_at,
        issued_at=issued_at,
        claims=dict(claims),
        access_token=token,
    )


_CLERK_COMPONENT_HTML = """
<section class="clerk-pilot-shell" aria-live="polite">
  <div class="clerk-pilot-heading">
    <div>
      <div class="clerk-pilot-eyebrow">AI COUNCIL · ISOLATED TEST</div>
      <h3>تسجيل الدخول التجريبي</h3>
      <p>مصادقة Clerk Development، مع تحقق خادمي من توقيع الجلسة قبل فتح بيانات الاختبار.</p>
    </div>
    <span class="clerk-pilot-environment">DEVELOPMENT</span>
  </div>
  <div id="ai-council-clerk-status" class="clerk-pilot-status">جارٍ تهيئة Clerk…</div>
  <div id="ai-council-clerk-signin" class="clerk-pilot-signin"></div>
  <div id="ai-council-clerk-user" class="clerk-pilot-user" hidden>
    <div id="ai-council-clerk-user-button"></div>
    <button id="ai-council-clerk-signout" type="button">تسجيل الخروج</button>
    <span id="ai-council-clerk-session-label"></span>
  </div>
</section>
"""

_CLERK_COMPONENT_CSS = """
.clerk-pilot-shell {
  border: 1px solid var(--st-border-color);
  border-radius: 16px;
  padding: 1.1rem;
  background: var(--st-card-background-color);
  color: var(--st-text-color);
  font-family: var(--st-font);
}
.clerk-pilot-heading {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
  margin-bottom: .85rem;
}
.clerk-pilot-eyebrow {
  font-size: .68rem;
  letter-spacing: .13em;
  font-weight: 700;
  opacity: .68;
}
.clerk-pilot-heading h3 {
  margin: .25rem 0;
  font-size: 1.25rem;
  color: var(--st-text-color);
}
.clerk-pilot-heading p {
  margin: 0;
  font-size: .88rem;
  line-height: 1.5;
  color: var(--st-text-color);
  opacity: .78;
}
.clerk-pilot-environment {
  border: 1px solid var(--st-border-color);
  border-radius: 999px;
  padding: .25rem .6rem;
  font-size: .66rem;
  font-weight: 700;
  white-space: nowrap;
}
.clerk-pilot-status {
  margin: .4rem 0 .75rem;
  color: var(--st-text-color);
  font-size: .86rem;
}
.clerk-pilot-signin { min-height: 80px; }
.clerk-pilot-user {
  display: flex;
  align-items: center;
  gap: .8rem;
  flex-wrap: wrap;
}
#ai-council-clerk-signout {
  border: 1px solid var(--st-border-color);
  border-radius: 8px;
  padding: .5rem .8rem;
  color: var(--st-text-color);
  background: transparent;
  cursor: pointer;
}
#ai-council-clerk-signout:hover {
  border-color: var(--st-primary-color);
}
#ai-council-clerk-session-label {
  font-size: .75rem;
  opacity: .7;
}
"""

_CLERK_COMPONENT_JS = r"""
export default function(component) {
  const { data, parentElement, setStateValue } = component;
  const root = parentElement.querySelector(".clerk-pilot-shell");
  if (!root) return () => {};

  const publishableKey = String((data || {}).publishable_key || "");
  const domain = String((data || {}).domain || "");
  const allowedOrigins = Array.isArray((data || {}).authorized_parties)
    ? data.authorized_parties.map(String) : [];
  const statusNode = root.querySelector("#ai-council-clerk-status");
  const signInNode = root.querySelector("#ai-council-clerk-signin");
  const userNode = root.querySelector("#ai-council-clerk-user");
  const userButtonNode = root.querySelector("#ai-council-clerk-user-button");
  const signOutButton = root.querySelector("#ai-council-clerk-signout");
  const sessionLabel = root.querySelector("#ai-council-clerk-session-label");
  let disposed = false;
  let clerk = null;
  let unsubscribe = null;
  let refreshTimer = null;
  let lastToken = "";
  let busy = false;

  const setStatus = (message) => {
    if (statusNode) statusNode.textContent = message;
  };

  const setBackendState = (status, token, error) => {
    if (disposed) return;
    setStateValue("auth_status", status);
    setStateValue("session_token", token || "");
    setStateValue("auth_error", error || "");
  };

  function loadScript(src, id) {
    return new Promise((resolve, reject) => {
      const existing = document.getElementById(id);
      if (existing && existing.dataset.loaded === "true") {
        resolve();
        return;
      }
      const script = existing || document.createElement("script");
      if (!existing) {
        script.id = id;
        script.src = src;
        script.async = true;
        script.crossOrigin = "anonymous";
        script.referrerPolicy = "strict-origin-when-cross-origin";
        document.head.appendChild(script);
      }
      const loaded = () => {
        script.dataset.loaded = "true";
        resolve();
      };
      const failed = () => reject(new Error("تعذر تحميل واجهة Clerk الرسمية."));
      script.addEventListener("load", loaded, { once: true });
      script.addEventListener("error", failed, { once: true });
      if (existing && window.__aiCouncilClerkScriptReady?.[id]) resolve();
    });
  }

  function mountSignedOut() {
    if (!clerk || disposed) return;
    try { clerk.unmountUserButton(userButtonNode); } catch (_) {}
    if (userNode) userNode.hidden = true;
    if (signInNode) signInNode.hidden = false;
    if (signInNode && !signInNode.dataset.mounted) {
      signInNode.dataset.mounted = "true";
      try {
        clerk.mountSignIn(signInNode, {
          fallbackRedirectUrl: window.location.href,
          signUpFallbackRedirectUrl: window.location.href
        });
      } catch (_) {
        signInNode.dataset.mounted = "";
        setStatus("تعذر عرض نموذج الدخول. أعد تحميل الصفحة.");
      }
    }
    setStatus("سجّل الدخول أو أنشئ حساب اختبار من خلال Clerk.");
    setBackendState("signed_out", "", "");
  }

  async function publishSession(session, user) {
    if (disposed || !session || busy) return;
    busy = true;
    try {
      const token = await session.getToken({ skipCache: true });
      if (disposed) return;
      if (!token || typeof token !== "string" || token.length > 16384) {
        throw new Error("لم يُرجع Clerk رمز جلسة صالحًا.");
      }
      if (token !== lastToken) {
        lastToken = token;
        setBackendState("signed_in_pending_verification", token, "");
      }
      if (userNode) userNode.hidden = false;
      if (signInNode) signInNode.hidden = true;
      if (signInNode && signInNode.dataset.mounted) {
        try { clerk.unmountSignIn(signInNode); } catch (_) {}
        signInNode.dataset.mounted = "";
      }
      if (userButtonNode && !userButtonNode.dataset.mounted) {
        userButtonNode.dataset.mounted = "true";
        try { clerk.mountUserButton(userButtonNode); } catch (_) {
          userButtonNode.dataset.mounted = "";
        }
      }
      const label = user?.primaryEmailAddress?.emailAddress
        || user?.username || user?.id || "مستخدم Clerk";
      if (sessionLabel) sessionLabel.textContent = String(label);
      setStatus("تم تسجيل الدخول. يتحقق الخادم الآن من توقيع JWT ومُصدره وصلاحيته…");
    } catch (_) {
      lastToken = "";
      setBackendState("token_error", "", "تعذر جلب رمز جلسة Clerk.");
      setStatus("تعذر الحصول على جلسة Clerk. أعد المحاولة.");
    } finally {
      busy = false;
    }
  }

  function mountAuthenticated() {
    if (!clerk || disposed) return;
    if (!clerk.session) {
      mountSignedOut();
      return;
    }
    publishSession(clerk.session, clerk.user);
  }

  async function initialize() {
    if (!publishableKey.startsWith("pk_test_") || domain !== "dear-hermit-1240.clerk.accounts.dev") {
      setStatus("إعداد Clerk لا يطابق بيئة Development التجريبية المعتمدة.");
      setBackendState("configuration_error", "", "Invalid test-only Clerk configuration.");
      return;
    }
    if (!allowedOrigins.includes(window.location.origin)) {
      setStatus("عنوان التطبيق الحالي غير مدرج ضمن Authorized Parties المسموح بها.");
      setBackendState("origin_blocked", "", "The current app origin is not allowlisted.");
      return;
    }

    try {
      const base = "https://" + domain + "/npm/";
      await loadScript(base + "@clerk/ui@1/dist/ui.browser.js", "ai-council-clerk-ui-js");
      await loadScript(base + "@clerk/clerk-js@6/dist/clerk.browser.js", "ai-council-clerk-js");
      if (disposed) return;
      if (typeof window.Clerk !== "function" || !window.__internal_ClerkUICtor) {
        throw new Error("ClerkJS UI bundle did not initialize.");
      }

      clerk = new window.Clerk(publishableKey);
      await clerk.load({
        ui: { ClerkUI: window.__internal_ClerkUICtor }
      });
      if (disposed) return;

      unsubscribe = clerk.addListener(({ session, user }) => {
        if (session === undefined) return;
        if (session === null) {
          lastToken = "";
          mountSignedOut();
          return;
        }
        publishSession(session, user);
      });

      if (clerk.session) {
        await mountAuthenticated();
        refreshTimer = window.setInterval(() => {
          if (clerk?.session) publishSession(clerk.session, clerk.user);
        }, 40000);
      } else {
        mountSignedOut();
      }
    } catch (_) {
      setStatus("تعذر تحميل Clerk أو الاتصال بخدمة المصادقة. تحقق من اتصال المتصفح وإعدادات Clerk.");
      setBackendState("initialization_error", "", "Clerk initialization failed.");
    }
  }

  const handleSignOut = async () => {
    if (!clerk) return;
    signOutButton.disabled = true;
    try {
      await clerk.signOut();
    } catch (_) {
      setStatus("تعذر إنهاء جلسة Clerk من الخادم. أعد المحاولة.");
    } finally {
      signOutButton.disabled = false;
    }
  };

  signOutButton?.addEventListener("click", handleSignOut);
  initialize();

  return () => {
    disposed = true;
    if (refreshTimer !== null) window.clearInterval(refreshTimer);
    if (typeof unsubscribe === "function") unsubscribe();
    signOutButton?.removeEventListener("click", handleSignOut);
    try { if (clerk && signInNode?.dataset.mounted) clerk.unmountSignIn(signInNode); } catch (_) {}
    try { if (clerk && userButtonNode?.dataset.mounted) clerk.unmountUserButton(userButtonNode); } catch (_) {}
  };
}
"""

_CLERK_AUTH_COMPONENT = component(
    "ai_council.clerk_streamlit_auth_v1",
    html=_CLERK_COMPONENT_HTML,
    css=_CLERK_COMPONENT_CSS,
    js=_CLERK_COMPONENT_JS,
    isolate_styles=True,
)


def render_clerk_login(st: Any) -> VerifiedClerkSession | None:
    """Render Clerk's official sign-in UI and verify every token on the server."""
    config = get_clerk_pilot_config(st)
    result = _CLERK_AUTH_COMPONENT(
        key=CLERK_COMPONENT_KEY,
        data={
            "publishable_key": config.publishable_key,
            "domain": config.domain,
            "authorized_parties": list(config.authorized_parties),
        },
        on_session_token_change=lambda: None,
        on_auth_status_change=lambda: None,
        on_auth_error_change=lambda: None,
    )
    status = getattr(result, "auth_status", "")
    error = getattr(result, "auth_error", "")
    token = getattr(result, "session_token", "")
    if isinstance(result, dict):
        status = result.get("auth_status", status)
        error = result.get("auth_error", error)
        token = result.get("session_token", token)

    if status in {"signed_out", "origin_blocked", "configuration_error", "initialization_error"}:
        st.session_state.pop(CLERK_SESSION_STATE_KEY, None)
        if error:
            st.warning(str(error))
        return None

    if not isinstance(token, str) or not token:
        return None
    try:
        verified = verify_clerk_session_token(
            token,
            issuer=config.issuer,
            authorized_parties=config.authorized_parties,
        )
    except ClerkPilotAuthError as exc:
        st.session_state.pop(CLERK_SESSION_STATE_KEY, None)
        if status == "signed_in_pending_verification":
            st.info("وصلت جلسة Clerk؛ يجري التحقق منها قبل فتح بيانات الاختبار.")
        else:
            st.error(str(exc))
        return None

    # Keep only the verified identity + short-lived access token in server-side
    # Streamlit session state. Never persist it to localStorage, URLs, logs, or files.
    st.session_state[CLERK_SESSION_STATE_KEY] = {
        "subject": verified.subject,
        "session_id": verified.session_id,
        "issuer": verified.issuer,
        "authorized_party": verified.authorized_party,
        "expires_at": verified.expires_at,
        "access_token": verified.access_token,
    }
    return verified


class ClerkPilotRepository:
    """PostgREST client for only the separate Clerk pilot table."""

    TABLE = "clerk_auth_pilot_records"

    def __init__(
        self,
        *,
        config: ClerkPilotConfig,
        session: Any,
    ) -> None:
        if not isinstance(session, VerifiedClerkSession):
            raise ValueError("A server-verified Clerk session is required.")
        if session.issuer != config.issuer:
            raise ValueError("Clerk session issuer does not match the test config.")
        self.config = config
        self.identity = session
        self._http = requests.Session()

    def _request(
        self,
        method: str,
        *,
        params: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        prefer: str = "",
    ) -> Any:
        headers = {
            "apikey": self.config.supabase_publishable_key,
            "Authorization": f"Bearer {self.identity.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        try:
            response = self._http.request(
                method,
                f"{self.config.supabase_url}/rest/v1/{self.TABLE}",
                params=params,
                json=payload,
                headers=headers,
                timeout=10,
            )
        except requests.RequestException:
            raise ClerkPilotAPIError(
                "تعذر الاتصال بقاعدة بيانات الاختبار. لم يتم تنفيذ العملية."
            ) from None

        if int(response.status_code) in (401, 403):
            raise ClerkPilotAPIError(
                "رفضت Supabase الرمز أو سياسة RLS هذه العملية."
            )
        if not 200 <= int(response.status_code) < 300:
            raise ClerkPilotAPIError(
                f"فشل طلب قاعدة بيانات الاختبار (HTTP {int(response.status_code)})."
            )
        if response.status_code == 204 or not getattr(response, "text", ""):
            return []
        try:
            return response.json()
        except (ValueError, json.JSONDecodeError):
            raise ClerkPilotAPIError("أعادت قاعدة البيانات استجابة غير صالحة.") from None

    def list_own(self) -> list[dict[str, Any]]:
        rows = self._request(
            "GET",
            params={
                "select": "record_id,record_key,record_payload,created_at,updated_at",
                "owner_subject": f"eq.{self.identity.subject}",
                "order": "created_at.desc",
                "limit": "50",
            },
        )
        if not isinstance(rows, list):
            raise ClerkPilotAPIError("قائمة سجلات الاختبار غير صالحة.")
        return rows

    def create_own(self, record_key: str, payload_text: str) -> dict[str, Any]:
        key = str(record_key or "").strip()
        value = str(payload_text or "")
        if not _RECORD_KEY_RE.fullmatch(key):
            raise ValueError("معرّف السجل يجب أن يكون 1–128 حرفًا من الحروف والأرقام والنقاط والشرطات.")
        if len(value) > MAX_RECORD_PAYLOAD_LENGTH:
            raise ValueError("محتوى السجل التجريبي يتجاوز 2000 حرف.")
        rows = self._request(
            "POST",
            payload={
                "owner_subject": self.identity.subject,
                "record_key": key,
                "record_payload": {"value": value},
            },
            prefer="return=representation",
        )
        if not isinstance(rows, list) or len(rows) != 1:
            raise ClerkPilotAPIError("لم تؤكد Supabase إنشاء سجل الاختبار.")
        return rows[0]

    def delete_own(self, record_id: str) -> bool:
        value = str(record_id or "").strip()
        try:
            uuid.UUID(value)
        except (ValueError, TypeError, AttributeError):
            raise ValueError("معرّف سجل الاختبار غير صالح.") from None
        rows = self._request(
            "DELETE",
            params={
                "record_id": f"eq.{value}",
                "owner_subject": f"eq.{self.identity.subject}",
                "select": "record_id",
            },
            prefer="return=representation",
        )
        return isinstance(rows, list) and len(rows) == 1

    def probe_owner_spoof_denial(self) -> bool:
        """Negative test: an authenticated Clerk user cannot write another owner."""
        spoof_subject = f"user_spoof_probe_{uuid.uuid4().hex}"
        probe_key = f"spoof-probe-{uuid.uuid4().hex[:16]}"
        payload = {
            "owner_subject": spoof_subject,
            "record_key": probe_key,
            "record_payload": {"probe": "must-be-rejected"},
        }
        headers = {
            "apikey": self.config.supabase_publishable_key,
            "Authorization": f"Bearer {self.identity.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        try:
            response = self._http.post(
                f"{self.config.supabase_url}/rest/v1/{self.TABLE}",
                json=payload,
                headers=headers,
                timeout=10,
            )
        except requests.RequestException:
            raise ClerkPilotAPIError(
                "تعذر تنفيذ اختبار منع انتحال المالك بسبب مشكلة اتصال."
            ) from None
        if response.status_code in (401, 403):
            return True
        if 200 <= response.status_code < 300:
            # A successful response is a fail-open result. Do not claim success.
            raise ClerkPilotAPIError(
                "فشل اختبار منع انتحال المالك: قبلت قاعدة البيانات محاولة كتابة باسم مستخدم آخر. "
                "أوقف الاختبار ولا تستخدم بيانات إنتاج."
            )
        raise ClerkPilotAPIError(
            f"تعذر تفسير نتيجة اختبار منع انتحال المالك (HTTP {response.status_code})."
        )
