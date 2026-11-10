from __future__ import annotations

import base64
import json
import time
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

import clerk_streamlit_auth as auth


ISSUER = "https://dear-hermit-1240.clerk.accounts.dev"
AUTHORIZED_PARTY = "https://ai-council-clerk-pilot-test.streamlit.app"
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



def test_pilot_config_requires_separate_test_origin_and_rejects_production():
    class MissingOrigin:
        secrets = {}

    with pytest.raises(auth.ClerkPilotAuthError, match="تطبيق الاختبار"):
        auth.get_clerk_pilot_config(MissingOrigin())

    class ProductionOrigin:
        secrets = {
            "CLERK_TEST_AUTHORIZED_PARTIES": auth.PRODUCTION_STREAMLIT_ORIGIN,
        }

    with pytest.raises(auth.ClerkPilotAuthError, match="عنوان تطبيق الإنتاج"):
        auth.get_clerk_pilot_config(ProductionOrigin())


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
    with pytest.raises(auth.ClerkPilotAuthError, match="غير موجود"):
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
