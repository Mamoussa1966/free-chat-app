from __future__ import annotations

import json
import time
import uuid

from cryptography.fernet import Fernet

import supabase_streamlit_auth as browser_auth
from supabase_auth import SupabaseAuthSession


PROJECT_URL = "https://council-auth-test.supabase.co"
PUBLISHABLE_KEY = "sb_publishable_unit_test_key"
USER_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeee0001"


class FakeStreamlit:
    def __init__(self, *, key=None):
        self.secrets = {
            "SUPABASE_URL": PROJECT_URL,
            "SUPABASE_PUBLISHABLE_KEY": PUBLISHABLE_KEY,
            "SUPABASE_AUTH_ENABLED": "true",
            "SUPABASE_SESSION_ENCRYPTION_KEY": key or Fernet.generate_key().decode("ascii"),
        }
        self.session_state = {}

    def warning(self, _message):
        raise AssertionError("unexpected warning during a configured restore")

    def error(self, _message):
        raise AssertionError("unexpected error during a configured restore")

    def html(self, _body, *, unsafe_allow_javascript=False):
        # The test double models Streamlit >=1.66, whose st.html supports this flag.
        assert unsafe_allow_javascript is True


def make_session() -> SupabaseAuthSession:
    return SupabaseAuthSession(
        access_token="ACCESS_TOKEN_DO_NOT_EXPOSE",
        refresh_token="REFRESH_TOKEN_DO_NOT_EXPOSE",
        expires_at=int(time.time()) + 3600,
        user_id=USER_ID,
        email="a@gmail.com",
        issuer=PROJECT_URL + "/auth/v1",
        verified_at=int(time.time()),
    )


def test_browser_session_is_encrypted_and_round_trips_without_plaintext():
    st = FakeStreamlit()
    state = make_session().to_state()

    token = browser_auth._seal_browser_session_state(st, state)

    assert token
    assert "ACCESS_TOKEN_DO_NOT_EXPOSE" not in token
    assert "REFRESH_TOKEN_DO_NOT_EXPOSE" not in token
    assert browser_auth._unseal_browser_session_state(st, token) == state


def test_browser_session_rejects_tampering_and_another_encryption_key():
    st = FakeStreamlit()
    token = browser_auth._seal_browser_session_state(st, make_session().to_state())
    wrong_key_st = FakeStreamlit(key=Fernet.generate_key().decode("ascii"))

    assert browser_auth._unseal_browser_session_state(wrong_key_st, token) is None
    tampered = token[:20] + ("A" if token[20] != "A" else "B") + token[21:]
    assert browser_auth._unseal_browser_session_state(st, tampered) is None


def test_browser_session_rejects_expired_envelopes_and_issuer_mismatch():
    st = FakeStreamlit()
    session_state = make_session().to_state()
    expired_envelope = {
        "version": 1,
        "saved_at": int(time.time()) - browser_auth._BROWSER_SESSION_MAX_AGE_SECONDS - 1,
        "issuer": PROJECT_URL + "/auth/v1",
        "session": session_state,
    }
    cipher = Fernet(st.secrets["SUPABASE_SESSION_ENCRYPTION_KEY"].encode("ascii"))
    expired_token = cipher.encrypt(
        json.dumps(expired_envelope, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    assert browser_auth._unseal_browser_session_state(st, expired_token) is None

    mismatched_state = dict(session_state, issuer="https://other-project.supabase.co/auth/v1")
    mismatched_token = browser_auth._seal_browser_session_state(st, mismatched_state)
    assert browser_auth._unseal_browser_session_state(st, mismatched_token) is None


def test_new_streamlit_session_recovers_and_revalidates_browser_session(monkeypatch):
    st = FakeStreamlit()
    session = make_session()
    payload = browser_auth._seal_browser_session_state(st, session.to_state())

    class FakeClient:
        def __init__(self):
            self.restored = None

        def restore_or_refresh(self, stored):
            self.restored = dict(stored)
            return session

    client = FakeClient()
    monkeypatch.setattr(browser_auth, "_client", lambda _st: client)
    monkeypatch.setattr(
        browser_auth,
        "_BROWSER_SESSION_COMPONENT",
        lambda **_kwargs: {"status": "ready", "payload": payload},
    )

    assert browser_auth.ensure_supabase_auth(st) is True
    assert client.restored == session.to_state()
    assert st.session_state[browser_auth.AUTH_SESSION_KEY]["user_id"] == USER_ID
    assert st.session_state[browser_auth.ACTIVE_SUBJECT_KEY] == USER_ID


def test_logout_clears_server_session_and_schedules_browser_clear(monkeypatch):
    st = FakeStreamlit()
    st.session_state[browser_auth.AUTH_SESSION_KEY] = make_session().to_state()
    signed_out = []

    class FakeClient:
        def sign_out(self, access_token):
            signed_out.append(access_token)

    monkeypatch.setattr(browser_auth, "_client", lambda _st: FakeClient())

    browser_auth.logout_supabase_user(st)

    assert signed_out == ["ACCESS_TOKEN_DO_NOT_EXPOSE"]
    assert browser_auth.AUTH_SESSION_KEY not in st.session_state
    assert st.session_state[browser_auth._PENDING_BROWSER_CLEAR] is True
    assert st.session_state[browser_auth._PENDING_BROWSER_CLEAR_ID]
