from __future__ import annotations

import json
import sys
import time
import types
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet, InvalidToken

import supabase_streamlit_auth as auth
from supabase_auth import SupabaseAuthSession


PROJECT_ISSUER = "https://council-auth-test.supabase.co/auth/v1"
USER_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeee0001"
ENCRYPTION_KEY = Fernet.generate_key().decode("ascii")


def make_session(*, access="access-token-A", refresh="refresh-token-A", verified_at=None):
    now = int(time.time())
    return SupabaseAuthSession(
        access_token=access,
        refresh_token=refresh,
        expires_at=now + 3600,
        user_id=USER_ID,
        email="a@example.org",
        issuer=PROJECT_ISSUER,
        verified_at=now - 600 if verified_at is None else verified_at,
    )


class FakeCookieManager:
    def __init__(self, key, jar, calls):
        self.key = key
        self.cookies = dict(jar)
        self.jar = jar
        self.calls = calls

    def set(self, cookie, value, **options):
        self.jar[cookie] = value
        self.cookies[cookie] = value
        self.calls.append(("set", cookie, value, options))

    def delete(self, cookie, key="delete"):
        self.jar.pop(cookie, None)
        self.cookies.pop(cookie, None)
        self.calls.append(("delete", cookie, key))


class FakeStreamlit:
    def __init__(self, *, cookies=None, encryption_key=ENCRYPTION_KEY):
        self.secrets = {
            "SUPABASE_AUTH_ENABLED": "true",
            "SUPABASE_URL": "https://council-auth-test.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_unit_test_key",
        }
        if encryption_key is not None:
            self.secrets["SUPABASE_SESSION_ENCRYPTION_KEY"] = encryption_key
        self.session_state = {}
        self.context = SimpleNamespace(cookies=dict(cookies or {}))
        self.messages = []

    def error(self, message):
        self.messages.append(("error", message))

    def warning(self, message):
        self.messages.append(("warning", message))

    def info(self, message):
        self.messages.append(("info", message))

    def title(self, message):
        self.messages.append(("title", message))

    def caption(self, message):
        self.messages.append(("caption", message))


class FakeAuthClient:
    issuer = PROJECT_ISSUER

    def __init__(self, session):
        self.session = session
        self.received_state = None
        self.calls = 0

    def restore_or_refresh(self, state):
        self.received_state = dict(state)
        self.calls += 1
        return self.session


@pytest.fixture
def fake_cookie_component(monkeypatch):
    jar = {}
    calls = []

    def factory(key="init"):
        return FakeCookieManager(key, jar, calls)

    monkeypatch.setitem(sys.modules, "extra_streamlit_components", types.SimpleNamespace(CookieManager=factory))
    return jar, calls


def test_encrypted_cookie_round_trips_session_without_exposing_tokens():
    session = make_session()
    fernet = Fernet(ENCRYPTION_KEY.encode("ascii"))

    token = auth._encode_session_cookie(session, fernet)

    assert session.access_token not in token
    assert session.refresh_token not in token
    restored = auth._decode_session_cookie(token, fernet, PROJECT_ISSUER)
    assert restored["access_token"] == session.access_token
    assert restored["refresh_token"] == session.refresh_token
    assert restored["user_id"] == USER_ID
    assert restored["issuer"] == PROJECT_ISSUER


def test_cookie_rejects_wrong_encryption_key_and_wrong_project_issuer():
    session = make_session()
    token = auth._encode_session_cookie(session, Fernet(ENCRYPTION_KEY.encode("ascii")))

    with pytest.raises(ValueError, match="Invalid session cookie"):
        auth._decode_session_cookie(token, Fernet(Fernet.generate_key()), PROJECT_ISSUER)

    with pytest.raises(ValueError, match="issuer"):
        auth._decode_session_cookie(token, Fernet(ENCRYPTION_KEY.encode("ascii")), "https://other.supabase.co/auth/v1")


def test_cookie_rejects_expired_or_tampered_payload():
    fernet = Fernet(ENCRYPTION_KEY.encode("ascii"))
    session_state = auth._session_state(make_session().to_state())
    payload = {
        "schema": auth.AUTH_COOKIE_SCHEMA,
        "created_at": int(time.time()) - auth.AUTH_COOKIE_TTL_SECONDS - 1,
        "session": session_state,
    }
    expired = fernet.encrypt_at_time(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"),
        current_time=int(time.time()) - auth.AUTH_COOKIE_TTL_SECONDS - 1,
    ).decode("ascii")
    with pytest.raises(ValueError, match="Invalid session cookie"):
        auth._decode_session_cookie(expired, fernet, PROJECT_ISSUER)

    with pytest.raises(ValueError, match="Invalid session cookie"):
        auth._decode_session_cookie("tampered-cookie-value", fernet, PROJECT_ISSUER)


def test_new_streamlit_connection_restores_verified_session_and_rotated_tokens(monkeypatch, fake_cookie_component):
    jar, cookie_calls = fake_cookie_component
    original = make_session()
    rotated = make_session(access="rotated-access-token", refresh="rotated-refresh-token")
    fernet = Fernet(ENCRYPTION_KEY.encode("ascii"))
    jar[auth.AUTH_COOKIE_NAME] = auth._encode_session_cookie(original, fernet)

    fresh_st = FakeStreamlit(cookies=jar)
    fake_client = FakeAuthClient(rotated)
    monkeypatch.setattr(auth, "_client", lambda _st: fake_client)

    assert auth.ensure_supabase_auth(fresh_st) is True
    assert fresh_st.session_state[auth.AUTH_SESSION_KEY]["user_id"] == USER_ID
    assert fresh_st.session_state[auth.AUTH_SESSION_KEY]["access_token"] == "rotated-access-token"
    assert fake_client.calls == 1
    assert fake_client.received_state["refresh_token"] == "refresh-token-A"

    persisted = jar[auth.AUTH_COOKIE_NAME]
    assert "rotated-access-token" not in persisted
    assert "rotated-refresh-token" not in persisted
    persisted_state = auth._decode_session_cookie(persisted, fernet, PROJECT_ISSUER)
    assert persisted_state["refresh_token"] == "rotated-refresh-token"
    set_call = next(call for call in cookie_calls if call[0] == "set")
    options = set_call[3]
    assert options["path"] == "/"
    assert options["secure"] is True
    assert options["same_site"] == "lax"
    assert options["max_age"] == auth.AUTH_COOKIE_TTL_SECONDS


def test_logout_removes_persistent_cookie_and_clears_user_state(monkeypatch, fake_cookie_component):
    jar, cookie_calls = fake_cookie_component
    session = make_session()
    jar[auth.AUTH_COOKIE_NAME] = auth._encode_session_cookie(session, Fernet(ENCRYPTION_KEY.encode("ascii")))
    st = FakeStreamlit(cookies=jar)
    st.session_state[auth.AUTH_SESSION_KEY] = session.to_state()
    st.session_state[auth.ACTIVE_SUBJECT_KEY] = USER_ID

    auth.logout_supabase_user(st)

    assert auth.AUTH_SESSION_KEY not in st.session_state
    assert auth.ACTIVE_SUBJECT_KEY not in st.session_state
    assert auth.AUTH_COOKIE_NAME not in jar
    assert any(call[0] == "delete" for call in cookie_calls)


def test_missing_or_invalid_encryption_key_disables_persistent_restore():
    no_key = FakeStreamlit(encryption_key=None)
    cipher, status = auth._fernet(no_key)
    assert cipher is None
    assert status == "missing"

    invalid_key = FakeStreamlit(encryption_key="not-a-fernet-key")
    cipher, status = auth._fernet(invalid_key)
    assert cipher is None
    assert status == "invalid"

def test_existing_authenticated_session_is_migrated_to_cookie_once(monkeypatch, fake_cookie_component):
    jar, cookie_calls = fake_cookie_component
    session = make_session()
    st = FakeStreamlit(cookies={})
    st.session_state[auth.AUTH_SESSION_KEY] = session.to_state()
    st.session_state[auth.ACTIVE_SUBJECT_KEY] = USER_ID
    fake_client = FakeAuthClient(session)
    monkeypatch.setattr(auth, "_client", lambda _st: fake_client)

    assert auth.ensure_supabase_auth(st) is True
    assert auth.AUTH_COOKIE_NAME in jar
    assert auth.AUTH_COOKIE_PERSISTED_STATE_KEY in st.session_state
    assert any(call[0] == "set" for call in cookie_calls)

    # A second ordinary rerun should not repeatedly issue the cookie write when
    # the original HTTP request had no cookie but the component command was sent.
    previous_writes = sum(1 for call in cookie_calls if call[0] == "set")
    assert auth.ensure_supabase_auth(st) is True
    assert sum(1 for call in cookie_calls if call[0] == "set") == previous_writes
