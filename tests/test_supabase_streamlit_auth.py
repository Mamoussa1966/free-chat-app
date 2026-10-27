from __future__ import annotations

import json
import time

import pytest
from cryptography.fernet import Fernet

import supabase_streamlit_auth as auth


PROJECT_URL = "https://council-auth-test.supabase.co"
ISSUER = PROJECT_URL + "/auth/v1"
USER_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeee0001"


class FakeSecrets(dict):
    pass


class FakeState(dict):
    pass


class FakeStreamlit:
    def __init__(self, key):
        self.secrets = FakeSecrets({
            "SUPABASE_AUTH_ENABLED": "true",
            "SUPABASE_URL": PROJECT_URL,
            "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_unit_test_key",
            "SUPABASE_SESSION_ENCRYPTION_KEY": key,
        })
        self.session_state = FakeState()


def session_state():
    now = int(time.time())
    return {
        "access_token": "access-token-A",
        "refresh_token": "refresh-token-A",
        "expires_at": now + 3600,
        "user_id": USER_ID,
        "email": "a@example.org",
        "issuer": ISSUER,
        "verified_at": now,
    }


def test_browser_session_envelope_is_encrypted_and_round_trips():
    key = Fernet.generate_key().decode("ascii")
    st = FakeStreamlit(key)
    state = session_state()

    token = auth._seal_browser_session_state(st, state)

    assert token
    assert state["access_token"] not in token
    assert state["refresh_token"] not in token
    assert auth._unseal_browser_session_state(st, token) == state


def test_browser_session_rejects_wrong_key():
    state = session_state()
    first = FakeStreamlit(Fernet.generate_key().decode("ascii"))
    second = FakeStreamlit(Fernet.generate_key().decode("ascii"))

    token = auth._seal_browser_session_state(first, state)

    assert auth._unseal_browser_session_state(second, token) is None


def test_browser_session_rejects_wrong_issuer():
    st = FakeStreamlit(Fernet.generate_key().decode("ascii"))
    state = session_state()
    token = auth._seal_browser_session_state(st, state)
    st.secrets["SUPABASE_URL"] = "https://different-project.supabase.co"

    assert auth._unseal_browser_session_state(st, token) is None


def test_browser_session_rejects_expired_and_tampered_envelopes():
    key = Fernet.generate_key().decode("ascii")
    st = FakeStreamlit(key)
    cipher = Fernet(key.encode("ascii"))
    old = int(time.time()) - auth._BROWSER_SESSION_MAX_AGE_SECONDS - 60
    envelope = {
        "version": 1,
        "saved_at": old,
        "issuer": ISSUER,
        "session": session_state(),
    }
    expired = cipher.encrypt_at_time(
        json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode("utf-8"),
        current_time=old,
    ).decode("ascii")

    assert auth._unseal_browser_session_state(st, expired) is None
    valid = auth._seal_browser_session_state(st, session_state())
    tampered = valid[:-1] + ("A" if valid[-1] != "A" else "B")
    assert auth._unseal_browser_session_state(st, tampered) is None


def test_missing_or_invalid_key_disables_browser_persistence():
    st = FakeStreamlit("not-a-fernet-key")
    assert auth._seal_browser_session_state(st, session_state()) == ""
    assert auth._unseal_browser_session_state(st, "not-a-token") is None
