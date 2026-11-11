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

import requests
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from streamlit.components.v2 import component


TEST_SUPABASE_URL = "https://pidcepvwsezdrlhxqksg.supabase.co"
TEST_CLERK_DOMAIN = "dear-hermit-1240.clerk.accounts.dev"
TEST_CLERK_PUBLISHABLE_KEY = (
    "pk_test_ZGVhci1oZXJtaXQtMTI0MC5jbGVyay5hY2NvdW50cy5kZXYk"
)
PRODUCTION_STREAMLIT_ORIGIN = (
    "https://free-chat-app-qmqyxzh2oe2n3qwcvqvpdh.streamlit.app"
)
TEST_CLERK_AUTHORIZED_ORIGIN = (
    "https://free-chat-app-vrbyn5tesfyhhz5skphzn5.streamlit.app"
)
TEST_SUPABASE_PUBLISHABLE_KEY = (
    "sb_publishable_DYeRykN5_v4KIpwfF6uY6A_yj18ggAz"
)

CLERK_SESSION_STATE_KEY = "_clerk_pilot_verified_session"
CLERK_ENV_DIAGNOSTICS_KEY = "_clerk_pilot_environment_diagnostics"
CLERK_COMPONENT_KEY = "ai_council_clerk_pilot_auth_v1"
MAX_SESSION_TOKEN_LENGTH = 16_384
MAX_RECORD_PAYLOAD_LENGTH = 2_000
_RECORD_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_DOMAIN_RE = re.compile(r"^[a-z0-9-]+\.clerk\.accounts\.dev$")

_JWKS_CACHE: dict[str, tuple[int, dict[str, RSAPublicKey]]] = {}
_JWKS_LAST_REFRESH: dict[str, int] = {}
_JWKS_LOCK = threading.RLock()
_B64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")


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

    # This pilot has exactly one deployed Streamlit origin. Pin it in code so
    # a missing or mistyped runtime secret cannot silently block Clerk login,
    # and never accept production or arbitrary caller-supplied origins.
    parties = (TEST_CLERK_AUTHORIZED_ORIGIN,)
    if PRODUCTION_STREAMLIT_ORIGIN in parties:
        raise ClerkPilotAuthError(
            "رُفض عنوان تطبيق الإنتاج. يجب استخدام Streamlit test app مستقل."
        )

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


def _decode_b64url(value: str, *, max_length: int) -> bytes:
    if not isinstance(value, str) or not value or len(value) > max_length or not _B64URL_RE.fullmatch(value):
        raise ClerkPilotAuthError("صيغة JWT غير صالحة.")
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception:
        raise ClerkPilotAuthError("تعذر فك ترميز JWT.") from None


def _decode_jwt_json(segment: str, *, max_length: int) -> dict[str, Any]:
    raw = _decode_b64url(segment, max_length=max_length)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError, TypeError):
        raise ClerkPilotAuthError("بنية JWT غير صالحة.") from None
    if not isinstance(value, dict):
        raise ClerkPilotAuthError("حقول JWT غير صالحة.")
    return value


def _fetch_jwks_document(issuer: str) -> dict[str, Any]:
    """Fetch only the fixed Clerk issuer's public JWKS; never follow token URLs."""
    try:
        response = requests.get(
            f"{issuer}/.well-known/jwks.json",
            headers={"Accept": "application/json"},
            timeout=5.0,
            allow_redirects=False,
        )
    except requests.RequestException:
        raise ClerkPilotAuthError("تعذر الاتصال بخدمة مفاتيح توقيع Clerk.") from None
    if int(getattr(response, "status_code", 0) or 0) != 200:
        raise ClerkPilotAuthError("خدمة مفاتيح توقيع Clerk أعادت استجابة غير صالحة.")
    body = getattr(response, "text", None)
    if not isinstance(body, str) or not body or len(body) > 131_072:
        raise ClerkPilotAuthError("حجم مفاتيح توقيع Clerk غير صالح.")
    try:
        document = json.loads(body)
    except (ValueError, TypeError, RecursionError):
        raise ClerkPilotAuthError("استجابة مفاتيح توقيع Clerk ليست JSON صالحًا.") from None
    if not isinstance(document, dict):
        raise ClerkPilotAuthError("بنية مفاتيح توقيع Clerk غير صالحة.")
    return document


def _jwk_to_rsa_public_key(jwk: dict[str, Any]) -> RSAPublicKey:
    if (
        jwk.get("kty") != "RSA"
        or jwk.get("use") not in (None, "sig")
        or jwk.get("alg") not in (None, "RS256")
        or not isinstance(jwk.get("n"), str)
        or not isinstance(jwk.get("e"), str)
    ):
        raise ClerkPilotAuthError("نوع مفتاح توقيع Clerk غير مقبول.")
    modulus_bytes = _decode_b64url(jwk["n"], max_length=4096)
    exponent_bytes = _decode_b64url(jwk["e"], max_length=32)
    modulus = int.from_bytes(modulus_bytes, "big")
    exponent = int.from_bytes(exponent_bytes, "big")
    try:
        public_key = rsa.RSAPublicNumbers(exponent, modulus).public_key()
    except (ValueError, TypeError):
        raise ClerkPilotAuthError("مفتاح RSA المنشور من Clerk غير صالح.") from None
    if public_key.key_size < 2048:
        raise ClerkPilotAuthError("مفتاح توقيع Clerk أقصر من الحد الأمني المطلوب.")
    return public_key


def _rsa_signing_key(
    issuer: str,
    kid: str,
    *,
    jwks_fetcher: Callable[[str], dict[str, Any]] | None = None,
    now: int | None = None,
) -> RSAPublicKey:
    """Return a cached RS256 signing key, with throttled refresh for key rotation."""
    current = int(time.time()) if now is None else int(now)
    with _JWKS_LOCK:
        cached = _JWKS_CACHE.get(issuer)
        if cached and cached[0] > current and kid in cached[1]:
            return cached[1][kid]

        # This throttle also applies when the last JWKS response did not contain
        # the requested kid (and therefore no positive key cache was created).
        last_refresh = _JWKS_LAST_REFRESH.get(issuer, 0)
        if last_refresh and current - last_refresh < 30:
            raise ClerkPilotAuthError(
                "مفتاح توقيع جلسة Clerk غير موجود في مجموعة المفاتيح الحالية."
            )

        fetch = jwks_fetcher or _fetch_jwks_document
        document = fetch(issuer)
        _JWKS_LAST_REFRESH[issuer] = current
        raw_keys = document.get("keys")
        if not isinstance(raw_keys, list) or not raw_keys or len(raw_keys) > 50:
            raise ClerkPilotAuthError("قائمة مفاتيح Clerk فارغة أو غير صالحة.")

        resolved: dict[str, RSAPublicKey] = {}
        seen_kids: set[str] = set()
        for item in raw_keys:
            if not isinstance(item, dict):
                continue
            item_kid = item.get("kid")
            if not isinstance(item_kid, str) or not item_kid or len(item_kid) > 128:
                continue
            if item_kid in seen_kids:
                raise ClerkPilotAuthError("استجابة JWKS تحتوي على معرّف مفتاح مكرر.")
            seen_kids.add(item_kid)
            if (
                item.get("kty") == "RSA"
                and item.get("use") in (None, "sig")
                and item.get("alg") in (None, "RS256")
            ):
                resolved[item_kid] = _jwk_to_rsa_public_key(item)

        if kid not in resolved:
            raise ClerkPilotAuthError("مفتاح توقيع جلسة Clerk غير منشور في JWKS المعتمد.")
        _JWKS_CACHE[issuer] = (current + 300, resolved)
        return resolved[kid]


def verify_clerk_session_token(
    token: str,
    *,
    issuer: str,
    authorized_parties: tuple[str, ...] | list[str],
    jwks_fetcher: Callable[[str], dict[str, Any]] | None = None,
    leeway_seconds: int = 15,
    now: int | None = None,
) -> VerifiedClerkSession:
    """Verify an RS256 Clerk session JWT signature and all authorization claims.

    The JWT header and payload are parsed only to locate the fixed issuer's
    public signing key and obtain claims. No claim is trusted until RS256
    verification succeeds. The JWKS URL is constructed from server config and
    is never read from the untrusted JWT header.
    """
    if not isinstance(token, str) or not token or len(token) > MAX_SESSION_TOKEN_LENGTH:
        raise ClerkPilotAuthError("جلسة Clerk غير موجودة أو تجاوزت الحجم المسموح.")
    if not isinstance(issuer, str) or issuer != f"https://{TEST_CLERK_DOMAIN}":
        raise ClerkPilotAuthError("مُصدر Clerk غير معتمد في بيئة الاختبار.")
    parties = tuple(_normalize_origin(x) for x in authorized_parties)
    if not parties:
        raise ClerkPilotAuthError("لا توجد واجهة تطبيق معتمدة لهذه الجلسة.")

    parts = token.split(".")
    if len(parts) != 3:
        raise ClerkPilotAuthError("رمز جلسة Clerk ليس JWT صالحًا.")
    header = _decode_jwt_json(parts[0], max_length=2048)
    if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
        raise ClerkPilotAuthError("خوارزمية أو معرّف مفتاح توقيع Clerk غير مقبول.")
    kid = header["kid"]
    if not kid or len(kid) > 128 or "crit" in header or header.get("b64") is False:
        raise ClerkPilotAuthError("معرّف أو خيارات مفتاح توقيع Clerk غير مقبولة.")

    claims = _decode_jwt_json(parts[1], max_length=8192)
    signing_key = _rsa_signing_key(
        issuer,
        kid,
        jwks_fetcher=jwks_fetcher,
        now=now,
    )
    signature = _decode_b64url(parts[2], max_length=2048)
    signed_message = f"{parts[0]}.{parts[1]}".encode("ascii")
    try:
        signing_key.verify(
            signature,
            signed_message,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except (InvalidSignature, ValueError, TypeError):
        raise ClerkPilotAuthError("توقيع جلسة Clerk غير صحيح.") from None

    required = ("exp", "iat", "nbf", "iss", "sub", "sid", "azp", "role")
    if any(name not in claims for name in required):
        raise ClerkPilotAuthError("جلسة Clerk تفتقد حقول المصادقة الإلزامية.")
    if claims.get("iss") != issuer:
        raise ClerkPilotAuthError("مُصدر جلسة Clerk لا يطابق بيئة الاختبار.")
    subject = claims.get("sub")
    session_id = claims.get("sid")
    authorized_party = claims.get("azp")
    if not isinstance(subject, str) or not subject.startswith("user_") or len(subject) > 255:
        raise ClerkPilotAuthError("جلسة Clerk لا تحتوي على User ID صالح.")
    if not isinstance(session_id, str) or not session_id.startswith("sess_") or len(session_id) > 255:
        raise ClerkPilotAuthError("جلسة Clerk لا تحتوي على Session ID صالح.")
    if claims.get("role") != "authenticated":
        raise ClerkPilotAuthError(
            "رمز Clerk لا يحمل دور authenticated المطلوب لتكامل Supabase."
        )
    if not isinstance(authorized_party, str) or _normalize_origin(authorized_party) not in parties:
        raise ClerkPilotAuthError(
            "هذا النطاق غير مدرج ضمن Authorized Parties المسموح بها لتطبيق الاختبار."
        )
    if claims.get("sts") == "pending":
        raise ClerkPilotAuthError("جلسة Clerk ما زالت قيد التهيئة ولا يُسمح لها بفتح البيانات.")

    numeric_claims: dict[str, int] = {}
    for name in ("exp", "iat", "nbf"):
        value = claims.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ClerkPilotAuthError(f"قيمة {name} في جلسة Clerk غير صالحة.")
        numeric_claims[name] = int(value)

    issued_at = numeric_claims["iat"]
    expires_at = numeric_claims["exp"]
    not_before = numeric_claims["nbf"]
    current = int(time.time()) if now is None else int(now)
    leeway = max(0, min(int(leeway_seconds), 30))
    if (
        issued_at > current + 30
        or not_before > current + leeway
        or expires_at <= current - leeway
        or expires_at <= issued_at
    ):
        raise ClerkPilotAuthError("انتهت صلاحية جلسة Clerk أو أن توقيتها غير صالح.")

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

  // Keep Clerk sign-in/sign-up inside this Streamlit page. Preserve the
  // page path and existing query parameters so OAuth returns to this pilot
  // page rather than the app home page or Clerk's hosted Account Portal.
  const FLOW_PARAM = "clerk_pilot_flow";
  const callbackParams = new Set([
    "intent",
    "redirect_url",
    "sign_in_force_redirect_url",
    "sign_up_force_redirect_url",
    "sign_in_fallback_redirect_url",
    "sign_up_fallback_redirect_url",
    "__clerk_db_jwt"
  ]);
  const currentUrl = new URL(window.location.href);
  const initialFlow = () => {
    const localFlow = currentUrl.searchParams.get(FLOW_PARAM);
    // OAuth callbacks may carry intent=signUp even when the sign-in attempt
    // was transferred. Honor the provider's intent for this initial render.
    if (currentUrl.searchParams.get("intent") === "signUp") return "sign-up";
    return localFlow === "sign-up" ? "sign-up" : "sign-in";
  };
  const selectedInitialFlow = initialFlow();
  const appBaseUrl = (() => {
    const url = new URL(currentUrl);
    for (const name of callbackParams) url.searchParams.delete(name);
    url.searchParams.delete(FLOW_PARAM);
    url.hash = "";
    return url;
  })();
  const appReturnUrl = appBaseUrl.toString();
  const flowUrl = (mode) => {
    const url = new URL(appBaseUrl);
    url.searchParams.set(FLOW_PARAM, mode);
    return url.toString();
  };
  // Keep Clerk Development's __clerk_db_jwt callback parameter intact until
  // Clerk.load() has consumed it. Removing it before initialization can leave
  // the development browser unauthenticated and prevent environment loading.
  function cleanConsumedCallbackUrl() {
    if (typeof window.history?.replaceState !== "function") return;
    const cleanUrl = new URL(appBaseUrl);
    cleanUrl.searchParams.set(FLOW_PARAM, selectedInitialFlow);
    window.history.replaceState(
      window.history.state || {},
      "",
      cleanUrl.pathname + cleanUrl.search
    );
  }

  const setStatus = (message) => {
    if (statusNode) statusNode.textContent = message;
  };

  const setBackendState = (status, token, error) => {
    if (disposed) return;
    setStateValue("auth_status", status);
    setStateValue("session_token", token || "");
    setStateValue("auth_error", error || "");
  };

  // Read the effective environment through the already initialized Clerk SDK.
  // This avoids a separate unauthenticated browser request to /v1/environment.
  function publishEnvironmentDiagnostics() {
    if (!clerk || disposed) return;
    try {
      const environment = clerk.__internal_environment;
      const attributes = environment?.userSettings?.attributes || {};
      const email = attributes.email_address;
      const password = attributes.password;
      // domain is the documented ClerkJS property. Keep the legacy
      // frontendApi fallback for older CDN builds.
      const frontendApi = String(clerk.domain || clerk.frontendApi || "")
        .toLowerCase()
        .replace(/^https?:\\/\\//, "")
        .split("/")[0];

      setStateValue("environment_status", environment ? "loaded" : "missing");
      setStateValue(
        "environment_email_enabled",
        typeof email?.enabled === "boolean" ? email.enabled : null
      );
      setStateValue(
        "environment_password_enabled",
        typeof password?.enabled === "boolean" ? password.enabled : null
      );
      setStateValue(
        "environment_email_verify_at_sign_up",
        typeof email?.verify_at_sign_up === "boolean" ? email.verify_at_sign_up : null
      );
      setStateValue(
        "environment_email_verifications",
        Array.isArray(email?.verifications) ? email.verifications : []
      );
      setStateValue("environment_sdk_version", String(clerk.version || ""));
      setStateValue("environment_ui_version", String(clerk.uiVersion || ""));
      setStateValue("environment_frontend_api", frontendApi);
      setStateValue("environment_domain_matches", frontendApi === domain.toLowerCase());
      setStateValue("environment_publishable_key_matches", clerk.publishableKey === publishableKey);
      setStateValue("environment_error_code", "");
    } catch (_) {
      setStateValue("environment_status", "read_error");
      setStateValue("environment_error_code", "environment_snapshot_unavailable");
    }
  }

  function loadScript(src, id, isReady, attributes = {}) {
    if (typeof isReady === "function" && isReady()) return Promise.resolve();
    window.__aiCouncilClerkScriptPromises = window.__aiCouncilClerkScriptPromises || {};
    if (window.__aiCouncilClerkScriptPromises[id]) {
      return window.__aiCouncilClerkScriptPromises[id];
    }
    const script = document.getElementById(id) || document.createElement("script");
    window.__aiCouncilClerkScriptPromises[id] = new Promise((resolve, reject) => {
      const loaded = () => {
        script.dataset.loaded = "true";
        resolve();
      };
      const failed = () => {
        delete window.__aiCouncilClerkScriptPromises[id];
        reject(new Error("تعذر تحميل واجهة Clerk الرسمية."));
      };
      script.addEventListener("load", loaded, { once: true });
      script.addEventListener("error", failed, { once: true });
      if (!script.isConnected) {
        script.id = id;
        script.src = src;
        script.async = true;
        script.crossOrigin = "anonymous";
        script.referrerPolicy = "strict-origin-when-cross-origin";
        Object.entries(attributes).forEach(([name, value]) => {
          script.setAttribute(name, String(value));
        });
        document.head.appendChild(script);
      } else if (script.dataset.loaded === "true" || (typeof isReady === "function" && isReady())) {
        resolve();
      }
    });
    return window.__aiCouncilClerkScriptPromises[id];
  }

  function handleFlowNavigation(event) {
    if (disposed) return;
    const path = typeof event.composedPath === "function" ? event.composedPath() : [];
    const anchor = path.find((node) => node && node.tagName === "A")
      || (event.target && typeof event.target.closest === "function"
        ? event.target.closest("a") : null);
    if (!anchor || !root.contains(anchor)) return;
    let target;
    try { target = new URL(anchor.href || anchor.getAttribute("href") || "", window.location.origin); }
    catch (_) { return; }
    const mode = target.searchParams.get(FLOW_PARAM);
    if (mode !== "sign-in" && mode !== "sign-up") return;
    event.preventDefault();
    event.stopPropagation();
    if (typeof event.stopImmediatePropagation === "function") event.stopImmediatePropagation();
    window.history.pushState({}, "", target.pathname + target.search + target.hash);
    mountSignedOut(mode);
  }

  function mountSignedOut(mode = "sign-in") {
    if (!clerk || disposed) return;
    try { clerk.unmountUserButton(userButtonNode); } catch (_) {}
    try { clerk.unmountSignIn(signInNode); } catch (_) {}
    try { clerk.unmountSignUp(signInNode); } catch (_) {}
    if (userButtonNode) userButtonNode.dataset.mounted = "";
    if (signInNode) {
      signInNode.dataset.mounted = "";
      signInNode.dataset.mode = "";
      signInNode.hidden = false;
    }
    if (userNode) userNode.hidden = true;

    const selectedMode = mode === "sign-up" ? "sign-up" : "sign-in";
    if (signInNode) {
      signInNode.dataset.mounted = "true";
      signInNode.dataset.mode = selectedMode;
      try {
        if (selectedMode === "sign-up") {
          clerk.mountSignUp(signInNode, {
            signInUrl: flowUrl("sign-in"),
            fallbackRedirectUrl: appReturnUrl,
            signInFallbackRedirectUrl: appReturnUrl
          });
        } else {
          clerk.mountSignIn(signInNode, {
            signUpUrl: flowUrl("sign-up"),
            fallbackRedirectUrl: appReturnUrl,
            signUpFallbackRedirectUrl: appReturnUrl,
            withSignUp: true,
            transferable: true
          });
        }
      } catch (_) {
        signInNode.dataset.mounted = "";
        signInNode.dataset.mode = "";
        setStatus("تعذر عرض نموذج المصادقة. أعد تحميل الصفحة.");
      }
    }
    setStatus(selectedMode === "sign-up"
      ? "أنشئ حساب اختبار جديدًا باستخدام البريد الإلكتروني."
      : "سجّل الدخول أو أنشئ حساب اختبار من خلال Clerk.");
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
      if (refreshTimer === null) {
        refreshTimer = window.setInterval(() => {
          if (clerk?.session) publishSession(clerk.session, clerk.user);
        }, 40000);
      }
      if (userNode) userNode.hidden = false;
      if (signInNode) signInNode.hidden = true;
      if (signInNode && signInNode.dataset.mounted) {
        try { clerk.unmountSignIn(signInNode); } catch (_) {}
        try { clerk.unmountSignUp(signInNode); } catch (_) {}
        signInNode.dataset.mounted = "";
        signInNode.dataset.mode = "";
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
      await loadScript(
        base + "@clerk/ui@1/dist/ui.browser.js",
        "ai-council-clerk-ui-js",
        () => !!window.__internal_ClerkUICtor
      );
      await loadScript(
        base + "@clerk/clerk-js@6/dist/clerk.browser.js",
        "ai-council-clerk-js",
        () => !!window.Clerk,
        { "data-clerk-publishable-key": publishableKey }
      );
      if (disposed) return;
      if (!window.Clerk || typeof window.Clerk.load !== "function" || !window.__internal_ClerkUICtor) {
        throw new Error("ClerkJS UI bundle did not initialize.");
      }

      // The CDN script creates the Clerk singleton from data-clerk-publishable-key.
      // This follows Clerk's documented script-tag setup (not the npm constructor path).
      clerk = window.Clerk;
      // Register both in-app routes on the Clerk instance itself. Clerk uses
      // these global URLs when an OAuth attempt must transfer between sign-in
      // and sign-up; component-level link props alone do not cover that flow.
      await clerk.load({
        signInUrl: flowUrl("sign-in"),
        signUpUrl: flowUrl("sign-up"),
        signInFallbackRedirectUrl: appReturnUrl,
        signUpFallbackRedirectUrl: appReturnUrl,
        afterSignOutUrl: flowUrl("sign-in"),
        ui: { ClerkUI: window.__internal_ClerkUICtor }
      });
      if (disposed) return;

      // Clerk has now consumed any __clerk_db_jwt callback token. Remove
      // transient OAuth/development parameters from browser history only now.
      cleanConsumedCallbackUrl();

      // Clerk.load() has already fetched and authenticated the environment.
      // Read the effective server-side values from that SDK-owned snapshot.
      publishEnvironmentDiagnostics();

      unsubscribe = clerk.addListener(({ session, user }) => {
        if (session === undefined) return;
        if (session === null) {
          lastToken = "";
          mountSignedOut("sign-in");
          return;
        }
        publishSession(session, user);
      });

      if (clerk.session) {
        await mountAuthenticated();
      } else {
        mountSignedOut(selectedInitialFlow);
      }
    } catch (error) {
      const firstError = Array.isArray(error?.errors) ? error.errors[0] : null;
      const errorCode = String(firstError?.code || error?.code || "");
      setStateValue("environment_status", "initialization_error");
      setStateValue("environment_error_code", errorCode || "clerk_initialization_failed");
      setStatus(
        errorCode === "dev_browser_unauthenticated"
          ? "رفض Clerk رمز متصفح التطوير. أعد تحميل صفحة الاختبار مرة واحدة؛ لا تفتح /v1/environment مباشرة."
          : "تعذر تحميل Clerk أو تهيئة بيئة المصادقة. راجع التشخيص المعروض أسفل الصفحة."
      );
      setBackendState("initialization_error", "", errorCode || "Clerk initialization failed.");
    }
  }

  const handleSignOut = async () => {
    if (!clerk) return;
    signOutButton.disabled = true;
    try {
      await clerk.signOut({ redirectUrl: flowUrl("sign-in") });
    } catch (_) {
      setStatus("تعذر إنهاء جلسة Clerk من الخادم. أعد المحاولة.");
    } finally {
      signOutButton.disabled = false;
    }
  };

  root.addEventListener("click", handleFlowNavigation, true);
  signOutButton?.addEventListener("click", handleSignOut);
  initialize();

  return () => {
    disposed = true;
    if (refreshTimer !== null) window.clearInterval(refreshTimer);
    if (typeof unsubscribe === "function") unsubscribe();
    root.removeEventListener("click", handleFlowNavigation, true);
    signOutButton?.removeEventListener("click", handleSignOut);
    try { if (clerk && signInNode?.dataset.mounted) clerk.unmountSignIn(signInNode); } catch (_) {}
    try { if (clerk && signInNode?.dataset.mounted) clerk.unmountSignUp(signInNode); } catch (_) {}
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

    def component_value(name: str, default: Any = None) -> Any:
        value = getattr(result, name, default)
        if isinstance(result, dict):
            value = result.get(name, value)
        return value

    diagnostics = {
        "status": component_value("environment_status", ""),
        "email_enabled": component_value("environment_email_enabled"),
        "password_enabled": component_value("environment_password_enabled"),
        "email_verify_at_sign_up": component_value("environment_email_verify_at_sign_up"),
        "email_verifications": component_value("environment_email_verifications", []),
        "sdk_version": component_value("environment_sdk_version", ""),
        "ui_version": component_value("environment_ui_version", ""),
        "frontend_api": component_value("environment_frontend_api", ""),
        "domain_matches": component_value("environment_domain_matches"),
        "publishable_key_matches": component_value("environment_publishable_key_matches"),
        "error_code": component_value("environment_error_code", ""),
    }
    if any(value not in ("", None, []) for value in diagnostics.values()):
        st.session_state[CLERK_ENV_DIAGNOSTICS_KEY] = diagnostics
    else:
        st.session_state.pop(CLERK_ENV_DIAGNOSTICS_KEY, None)

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
