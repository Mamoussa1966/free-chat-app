from __future__ import annotations

import base64
import json
import re
import time
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

import clerk_streamlit_auth as auth


ISSUER = "https://dear-hermit-1240.clerk.accounts.dev"
AUTHORIZED_PARTY = "https://free-chat-app-vrbyn5tesfyhhz5skphzn5.streamlit.app"
USER_A = "user_test_A"
SESSION_A = "sess_test_A"
TEST_KID = "clerk-pilot-test-key"


@pytest.fixture(scope="module")
def signing_keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return {
        "private": private,
        "public": private.public_key(),
        "other_private": other_private,
    }


@pytest.fixture(autouse=True)
def clear_jwks_cache():
    auth._JWKS_CACHE.clear()
    auth._JWKS_LAST_REFRESH.clear()


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def b64url_int(value: int) -> str:
    return b64url(value.to_bytes((value.bit_length() + 7) // 8, "big"))


def jwks_document(public_key):
    numbers = public_key.public_numbers()
    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": TEST_KID,
                "n": b64url_int(numbers.n),
                "e": b64url_int(numbers.e),
            }
        ]
    }


def make_claims(**updates):
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "sub": USER_A,
        "sid": SESSION_A,
        "azp": AUTHORIZED_PARTY,
        "role": "authenticated",
        "iat": now - 10,
        "nbf": now - 10,
        "exp": now + 120,
    }
    claims.update(updates)
    return claims


def make_token(private_key, *, claims=None, alg="RS256", kid=TEST_KID):
    header = {"alg": alg, "kid": kid, "typ": "JWT"}
    payload = claims if claims is not None else make_claims()
    encoded_header = b64url(json.dumps(header, separators=(",", ":")).encode())
    encoded_payload = b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{encoded_header}.{encoded_payload}.{b64url(signature)}"


def verifier_options(public_key):
    doc = jwks_document(public_key)
    return {
        "issuer": ISSUER,
        "authorized_parties": (AUTHORIZED_PARTY,),
        "jwks_fetcher": lambda _issuer: doc,
    }


def test_publishable_key_decodes_only_the_pinned_development_domain():
    assert auth._decode_publishable_domain(auth.TEST_CLERK_PUBLISHABLE_KEY) == auth.TEST_CLERK_DOMAIN


def test_publishable_key_rejects_live_or_unexpected_domain():
    with pytest.raises(auth.ClerkPilotAuthError):
        auth._decode_publishable_domain("pk_live_fake")
    wrong_domain = "pk_test_aW52YWxpZC5jbGVyay5hY2NvdW50cy5kZXYk"
    assert auth._decode_publishable_domain(wrong_domain) == "invalid.clerk.accounts.dev"

    class FakeStreamlit:
        secrets = {
            "CLERK_TEST_PUBLISHABLE_KEY": wrong_domain,
            "CLERK_TEST_DOMAIN": "invalid.clerk.accounts.dev",
        }

    with pytest.raises(auth.ClerkPilotAuthError):
        auth.get_clerk_pilot_config(FakeStreamlit())


def test_pilot_config_is_pinned_to_the_test_project_and_authorized_origin():
    class FakeStreamlit:
        secrets = {
            "CLERK_TEST_AUTHORIZED_PARTIES": AUTHORIZED_PARTY,
        }

    config = auth.get_clerk_pilot_config(FakeStreamlit())
    assert config.domain == auth.TEST_CLERK_DOMAIN
    assert config.issuer == ISSUER
    assert config.supabase_url == auth.TEST_SUPABASE_URL
    assert config.authorized_parties == (AUTHORIZED_PARTY,)



def test_pilot_config_is_pinned_to_the_only_deployed_test_origin():
    class MissingOrigin:
        secrets = {}

    config = auth.get_clerk_pilot_config(MissingOrigin())
    assert config.authorized_parties == (auth.TEST_CLERK_AUTHORIZED_ORIGIN,)

    class MisconfiguredOrigin:
        secrets = {
            "CLERK_TEST_AUTHORIZED_PARTIES": "https://wrong-origin.example",
        }

    # Runtime secrets cannot widen or redirect the trusted origin.
    assert auth.get_clerk_pilot_config(MisconfiguredOrigin()).authorized_parties == (
        auth.TEST_CLERK_AUTHORIZED_ORIGIN,
    )


def test_pilot_config_rejects_wrong_clerk_instance():
    class FakeStreamlit:
        secrets = {"CLERK_TEST_DOMAIN": "some-other.clerk.accounts.dev"}

    with pytest.raises(auth.ClerkPilotAuthError):
        auth.get_clerk_pilot_config(FakeStreamlit())


def test_valid_clerk_session_token_is_verified_and_subject_bound(signing_keys):
    token = make_token(signing_keys["private"])
    verified = auth.verify_clerk_session_token(token, **verifier_options(signing_keys["public"]))
    assert verified.subject == USER_A
    assert verified.session_id == SESSION_A
    assert verified.issuer == ISSUER
    assert verified.authorized_party == AUTHORIZED_PARTY
    assert verified.expires_at > int(time.time())
    assert verified.access_token == token


def test_wrong_signature_is_rejected(signing_keys):
    token = make_token(signing_keys["other_private"])
    with pytest.raises(auth.ClerkPilotAuthError, match="توقيع"):
        auth.verify_clerk_session_token(token, **verifier_options(signing_keys["public"]))


def test_wrong_issuer_is_rejected_even_when_token_is_signed(signing_keys):
    token = make_token(signing_keys["private"], claims=make_claims(iss="https://attacker.example"))
    with pytest.raises(auth.ClerkPilotAuthError, match="مُصدر"):
        auth.verify_clerk_session_token(token, **verifier_options(signing_keys["public"]))


def test_wrong_authorized_party_is_rejected(signing_keys):
    token = make_token(signing_keys["private"], claims=make_claims(azp="https://attacker.example"))
    with pytest.raises(auth.ClerkPilotAuthError, match="Authorized Parties"):
        auth.verify_clerk_session_token(token, **verifier_options(signing_keys["public"]))


def test_missing_role_is_rejected(signing_keys):
    claims = make_claims()
    claims.pop("role")
    token = make_token(signing_keys["private"], claims=claims)
    with pytest.raises(auth.ClerkPilotAuthError, match="الإلزامية"):
        auth.verify_clerk_session_token(token, **verifier_options(signing_keys["public"]))


def test_wrong_role_is_rejected(signing_keys):
    token = make_token(signing_keys["private"], claims=make_claims(role="anon"))
    with pytest.raises(auth.ClerkPilotAuthError, match="authenticated"):
        auth.verify_clerk_session_token(token, **verifier_options(signing_keys["public"]))


def test_expired_token_is_rejected(signing_keys):
    token = make_token(signing_keys["private"], claims=make_claims(exp=int(time.time()) - 60))
    with pytest.raises(auth.ClerkPilotAuthError, match="توقيتها"):
        auth.verify_clerk_session_token(token, **verifier_options(signing_keys["public"]))


def test_token_without_required_session_claims_is_rejected(signing_keys):
    claims = make_claims()
    claims.pop("sid")
    token = make_token(signing_keys["private"], claims=claims)
    with pytest.raises(auth.ClerkPilotAuthError, match="الإلزامية"):
        auth.verify_clerk_session_token(token, **verifier_options(signing_keys["public"]))


def test_token_size_and_algorithm_are_fail_closed(signing_keys):
    with pytest.raises(auth.ClerkPilotAuthError):
        auth.verify_clerk_session_token(
            "x" * (auth.MAX_SESSION_TOKEN_LENGTH + 1),
            issuer=ISSUER,
            authorized_parties=(AUTHORIZED_PARTY,),
        )
    token = make_token(signing_keys["private"], alg="HS256")
    with pytest.raises(auth.ClerkPilotAuthError, match="خوارزمية"):
        auth.verify_clerk_session_token(token, **verifier_options(signing_keys["public"]))


def test_unknown_kid_forces_jwks_refresh_then_fails_closed(signing_keys):
    token = make_token(signing_keys["private"], kid="not-in-jwks")
    with pytest.raises(auth.ClerkPilotAuthError, match="غير منشور"):
        auth.verify_clerk_session_token(token, **verifier_options(signing_keys["public"]))



def test_unknown_kid_refresh_is_rate_limited(signing_keys):
    token = make_token(signing_keys["private"], kid="unknown-key")
    doc = jwks_document(signing_keys["public"])
    calls = []

    def fetch(_issuer):
        calls.append(1)
        return doc

    options = {
        "issuer": ISSUER,
        "authorized_parties": (AUTHORIZED_PARTY,),
        "jwks_fetcher": fetch,
        "now": 1000,
    }
    with pytest.raises(auth.ClerkPilotAuthError, match="غير منشور|غير موجود"):
        auth.verify_clerk_session_token(token, **options)
    assert len(calls) == 1

    options["now"] = 1001
    with pytest.raises(auth.ClerkPilotAuthError, match="غير موجود"):
        auth.verify_clerk_session_token(token, **options)
    assert len(calls) == 1


def test_clerk_cdn_uses_documented_publishable_key_bootstrap_and_no_constructor():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "clerk_streamlit_auth.py").read_text(encoding="utf-8")
    assert '"data-clerk-publishable-key": publishableKey' in source
    assert "clerk = window.Clerk;" in source
    assert "new window.Clerk(" not in source
    assert "window.__internal_ClerkUICtor" in source


def test_environment_diagnostics_read_effective_sdk_snapshot_not_an_unauthenticated_fetch():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "clerk_streamlit_auth.py").read_text(encoding="utf-8")
    assert "clerk.__internal_environment" in source
    assert "attributes.email_address" in source
    assert "attributes.password" in source
    assert re.search(r'setStateValue\(\s*"environment_email_enabled"', source)
    assert re.search(r'setStateValue\(\s*"environment_password_enabled"', source)
    assert 'setStateValue("environment_domain_matches"' in source
    assert "clerk.domain || clerk.frontendApi" in source
    assert "fetch(\"https://dear-hermit-1240.clerk.accounts.dev/v1/environment\"" not in source


def test_dev_browser_callback_token_is_preserved_until_clerk_load_completes():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "clerk_streamlit_auth.py").read_text(encoding="utf-8")
    assert '"__clerk_db_jwt"' in source
    assert "function cleanConsumedCallbackUrl()" in source
    assert source.index("await clerk.load({") < source.index("cleanConsumedCallbackUrl();")


def test_environment_diagnostic_state_values_are_registered_with_streamlit():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "clerk_streamlit_auth.py").read_text(encoding="utf-8")
    diagnostic_states = (
        "environment_status",
        "environment_email_enabled",
        "environment_password_enabled",
        "environment_email_verify_at_sign_up",
        "environment_email_verifications",
        "environment_sdk_version",
        "environment_ui_version",
        "environment_frontend_api",
        "environment_domain_matches",
        "environment_publishable_key_matches",
        "environment_error_code",
    )
    for state in diagnostic_states:
        assert f"on_{state}_change=lambda: None" in source


def test_sign_in_and_sign_up_switch_inside_pilot_without_account_portal_navigation():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "clerk_streamlit_auth.py").read_text(encoding="utf-8")
    assert 'signUpUrl: flowUrl("sign-up")' in source
    assert 'signInUrl: flowUrl("sign-in")' in source
    assert 'id="ai-council-clerk-signin-code"' in source
    assert 'id="ai-council-clerk-signin-start"' in source
    assert 'signIn.create({ identifier, password })' in source
    assert 'if (!/^\\d{4,12}$/.test(code))' in source
    assert 'prepareSecondFactor({' in source
    assert 'attemptSecondFactor({ strategy: "email_code", code })' in source
    assert 'attemptFirstFactor({ strategy: "email_code", code })' in source
    assert 'clerk.setActive({ session: attempt.createdSessionId })' in source
    assert 'function mountCustomSignIn()' in source
    assert 'لم نطلب إرسال رمز جديد.' in source
    assert 'signInUrl: flowUrl("sign-in")' in source
    assert 'signUpUrl: flowUrl("sign-up")' in source
    assert 'currentUrl.searchParams.get("intent") === "signUp"' in source
    assert 'mountSignedOut(selectedInitialFlow)' in source
    assert "let activeFlow = selectedInitialFlow;" in source
    assert "activeFlow = selectedMode;" in source
    assert "mountSignedOut(activeFlow);" in source
    assert 'afterSignOutUrl: flowUrl("sign-in")' in source
    assert 'clerk.signOut({ redirectUrl: flowUrl("sign-in") })' in source
    assert 'callbackParams' in source
    assert 'url.searchParams.delete(name)' in source
    assert 'root.addEventListener("click", handleFlowNavigation, true)' in source
    assert 'event.preventDefault()' in source
    assert 'const FLOW_PARAM = "clerk_pilot_flow"' in source
    assert 'https://dear-hermit-1240.accounts.dev' not in source


def test_clerk_email_sign_up_has_an_explicit_email_code_input_and_verify_button():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "clerk_streamlit_auth.py").read_text(encoding="utf-8")
    assert 'id="ai-council-clerk-signup-code"' in source
    assert 'autocomplete="one-time-code"' in source
    assert 'تحقق وأكمل التسجيل' in source
    assert 'إعادة إرسال الرمز' in source
    assert 'function currentSignUpAttempt()' in source
    assert 'return clerk?.client?.signUp || null;' in source
    assert 'signUp.create({ emailAddress, password })' in source
    assert 'prepareEmailAddressVerification({ strategy: "email_code" })' in source
    assert 'attemptEmailAddressVerification({ code })' in source
    assert 'clerk.setActive({ session: attempt.createdSessionId })' in source
    assert 'if (signUpPanel) signUpPanel.hidden = true;' in source




def test_clerk_email_password_sign_in_has_an_explicit_code_verification_step():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "clerk_streamlit_auth.py").read_text(encoding="utf-8")
    assert 'id="ai-council-clerk-signin-email"' in source
    assert 'id="ai-council-clerk-signin-password"' in source
    assert 'id="ai-council-clerk-signin-code"' in source
    assert 'autocomplete="one-time-code"' in source
    assert 'signIn.create({ identifier, password })' in source
    assert 'if (!/^\\d{4,12}$/.test(code))' in source
    assert 'prepareSecondFactor({' in source
    assert 'attemptSecondFactor({ strategy: "email_code", code })' in source
    assert 'attemptFirstFactor({ strategy: "email_code", code })' in source
    assert 'clerk.setActive({ session: attempt.createdSessionId })' in source
    assert 'signInStartForm?.addEventListener("submit", handleSignInStart)' in source
    assert 'signInVerifyForm?.addEventListener("submit", handleSignInVerify)' in source
    assert 'clerk.mountSignIn(signInNode' not in source


def test_pending_clerk_sign_in_verification_is_resumed_without_resending_code():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "clerk_streamlit_auth.py").read_text(encoding="utf-8")
    assert 'pending?.status === "needs_second_factor"' in source
    assert 'pending?.status === "needs_first_factor"' in source
    assert 'يوجد طلب تحقق لتسجيل الدخول. أدخل الرمز الذي وصلك؛ لم نطلب إرسال رمز جديد.' in source


def test_clerk_sign_up_resumes_pending_email_verification_without_automatic_resend():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "clerk_streamlit_auth.py").read_text(encoding="utf-8")
    assert 'pending?.status === "missing_requirements"' in source
    assert 'pending.unverifiedFields.includes("emailAddress")' in source
    assert 'showSignUpVerification(\n        pending.emailAddress,' in source
    assert 'تم استرجاع طلب التسجيل غير المكتمل من جلسة Clerk الحالية.' in source
    assert 'استخدم أحدث رمز وصلك؛ لن ننشئ حسابًا جديدًا.' in source


def test_clerk_sign_up_surfaces_rate_limit_and_existing_account_errors_without_retrying():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "clerk_streamlit_auth.py").read_text(encoding="utf-8")
    assert 'code === "too_many_requests"' in source
    assert 'code === "form_identifier_exists"' in source
    assert 'Clerk يفرض تقييدًا مؤقتًا للمحاولات.' in source
    assert 'هذا البريد مرتبط بحساب موجود بالفعل.' in source
    assert 'لدي حساب بالفعل — تسجيل الدخول' in source
    assert 'signUpStartBackButton?.addEventListener("click", handleSignUpBack)' in source


def test_repository_uses_verified_identity_and_clerk_bearer_token(signing_keys):
    token = make_token(signing_keys["private"])
    verified = auth.verify_clerk_session_token(token, **verifier_options(signing_keys["public"]))
    config = auth.ClerkPilotConfig(
        publishable_key=auth.TEST_CLERK_PUBLISHABLE_KEY,
        domain=auth.TEST_CLERK_DOMAIN,
        issuer=ISSUER,
        authorized_parties=(AUTHORIZED_PARTY,),
        supabase_url=auth.TEST_SUPABASE_URL,
        supabase_publishable_key=auth.TEST_SUPABASE_PUBLISHABLE_KEY,
    )
    repository = auth.ClerkPilotRepository(config=config, session=verified)
    calls = []

    class FakeResponse:
        status_code = 201
        text = '[{"record_id":"00000000-0000-0000-0000-000000000001"}]'

        def json(self):
            return [{"record_id": "00000000-0000-0000-0000-000000000001"}]

    class FakeHTTP:
        def request(self, method, url, **kwargs):
            calls.append((method, url, kwargs))
            return FakeResponse()

    repository._http = FakeHTTP()
    result = repository.create_own("first-record", "test only")
    assert result["record_id"] == "00000000-0000-0000-0000-000000000001"
    method, url, kwargs = calls[0]
    assert method == "POST"
    assert url.endswith("/rest/v1/clerk_auth_pilot_records")
    assert kwargs["headers"]["Authorization"] == f"Bearer {token}"
    assert kwargs["json"]["owner_subject"] == USER_A


def test_repository_rejects_invalid_record_keys(signing_keys):
    token = make_token(signing_keys["private"])
    verified = auth.verify_clerk_session_token(token, **verifier_options(signing_keys["public"]))
    config = auth.ClerkPilotConfig(
        publishable_key=auth.TEST_CLERK_PUBLISHABLE_KEY,
        domain=auth.TEST_CLERK_DOMAIN,
        issuer=ISSUER,
        authorized_parties=(AUTHORIZED_PARTY,),
        supabase_url=auth.TEST_SUPABASE_URL,
        supabase_publishable_key=auth.TEST_SUPABASE_PUBLISHABLE_KEY,
    )
    repository = auth.ClerkPilotRepository(config=config, session=verified)
    with pytest.raises(ValueError):
        repository.create_own("bad key with spaces", "payload")


def test_repository_denial_probe_passes_only_on_401_or_403(signing_keys):
    token = make_token(signing_keys["private"])
    verified = auth.verify_clerk_session_token(token, **verifier_options(signing_keys["public"]))
    config = auth.ClerkPilotConfig(
        publishable_key=auth.TEST_CLERK_PUBLISHABLE_KEY,
        domain=auth.TEST_CLERK_DOMAIN,
        issuer=ISSUER,
        authorized_parties=(AUTHORIZED_PARTY,),
        supabase_url=auth.TEST_SUPABASE_URL,
        supabase_publishable_key=auth.TEST_SUPABASE_PUBLISHABLE_KEY,
    )
    repository = auth.ClerkPilotRepository(config=config, session=verified)

    class FakeResponse:
        status_code = 403

    class FakeHTTP:
        def post(self, *_args, **_kwargs):
            return FakeResponse()

    repository._http = FakeHTTP()
    assert repository.probe_owner_spoof_denial() is True



def test_signed_out_user_container_is_hidden_despite_flex_layout():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "clerk_streamlit_auth.py").read_text(encoding="utf-8")
    assert ".clerk-pilot-user[hidden]" in source
    assert "display: none !important;" in source
    assert "if (userNode) userNode.hidden = true;" in source
