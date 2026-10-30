from __future__ import annotations

import json
import time
from pathlib import Path

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


def _make_test_recovery_jwt(issuer: str) -> str:
    import base64

    payload = base64.urlsafe_b64encode(
        json.dumps({"iss": issuer}).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return "header." + payload + ".signature"


def test_test_project_recovery_token_selects_only_allowlisted_test_client(monkeypatch):
    st = FakeStreamlit(Fernet.generate_key().decode("ascii"))
    st.secrets["SUPABASE_TEST_PUBLISHABLE_KEY"] = "sb_publishable_test_only"
    created = []

    class FakeClient:
        def __init__(self, *, supabase_url, publishable_key):
            created.append((supabase_url, publishable_key))

    monkeypatch.setattr(auth, "SupabaseAuthClient", FakeClient)
    token = _make_test_recovery_jwt("https://pidcepvwsezdrlhxqksg.supabase.co/auth/v1")

    client, project_kind = auth._client_for_recovery_token(st, token)

    assert project_kind == "test"
    assert isinstance(client, FakeClient)
    assert created == [(
        "https://pidcepvwsezdrlhxqksg.supabase.co",
        "sb_publishable_test_only",
    )]


def test_recovery_issuer_rejects_unknown_project_before_network(monkeypatch):
    st = FakeStreamlit(Fernet.generate_key().decode("ascii"))
    token = _make_test_recovery_jwt("https://unapproved.supabase.co/auth/v1")

    with pytest.raises(auth.SupabaseAuthError, match="لا يتبع"):
        auth._client_for_recovery_token(st, token)


def test_recovery_callback_is_verified_with_project_user_endpoint_and_scoped_to_test_account(monkeypatch):
    st = FakeStreamlit(Fernet.generate_key().decode("ascii"))
    calls = []

    class FakeClient:
        issuer = "https://pidcepvwsezdrlhxqksg.supabase.co/auth/v1"

        def get_verified_user(self, token):
            calls.append(token)
            return {
                "id": USER_ID,
                "email": "verified-test-user@example.invalid",
            }

    monkeypatch.setattr(
        auth,
        "_client_for_recovery_token",
        lambda _st, token: (FakeClient(), "test"),
    )
    monkeypatch.setattr(auth, "_recovery_account_label", lambda _email: "A")

    handled = auth._capture_password_recovery(st, {
        "status": "password_recovery",
        "recovery_id": "one-time-recovery-id",
        "access_token": "recovery-access-token",
        "refresh_token": "recovery-refresh-token",
        "expires_in": 900,
    })

    assert handled is True
    assert calls == ["recovery-access-token"]
    recovered = st.session_state[auth._RECOVERY_STATE_KEY]
    assert recovered["user_id"] == USER_ID
    assert recovered["project_kind"] == "test"
    assert recovered["account_label"] == "A"
    assert recovered["access_token"] == "recovery-access-token"


def test_recovery_callback_never_trusts_email_or_identity_before_auth_user_verification(monkeypatch):
    st = FakeStreamlit(Fernet.generate_key().decode("ascii"))

    class RejectingClient:
        issuer = "https://pidcepvwsezdrlhxqksg.supabase.co/auth/v1"

        def get_verified_user(self, _token):
            raise auth.SupabaseAuthError("invalid recovery token")

    monkeypatch.setattr(
        auth,
        "_client_for_recovery_token",
        lambda _st, _token: (RejectingClient(), "test"),
    )

    handled = auth._capture_password_recovery(st, {
        "status": "password_recovery",
        "recovery_id": "bad-recovery",
        "access_token": "unverified-access-token",
        "refresh_token": "unverified-refresh-token",
    })

    assert handled is True
    assert auth._RECOVERY_STATE_KEY not in st.session_state
    assert st.session_state[auth._AUTH_NOTICE_KEY]


def test_test_password_recovery_updates_only_with_recovery_session_and_does_not_activate_test_session(monkeypatch):
    from contextlib import nullcontext

    st = FakeStreamlit(Fernet.generate_key().decode("ascii"))
    st.session_state[auth._RECOVERY_STATE_KEY] = {
        "access_token": "test-recovery-access",
        "refresh_token": "test-recovery-refresh",
        "expires_at": int(time.time()) + 900,
        "user_id": USER_ID,
        "email": "verified-test-user@example.invalid",
        "issuer": "https://pidcepvwsezdrlhxqksg.supabase.co/auth/v1",
        "project_kind": "test",
        "account_label": "A",
    }
    updates = []

    class FakeClient:
        def __init__(self, *, supabase_url, publishable_key):
            assert supabase_url == "https://pidcepvwsezdrlhxqksg.supabase.co"
            assert publishable_key == auth._TEST_PROJECT_PUBLISHABLE_KEY

        def update_password(self, access_token, password):
            updates.append((access_token, password))
            return {"id": USER_ID, "email": "verified-test-user@example.invalid"}

    monkeypatch.setattr(auth, "SupabaseAuthClient", FakeClient)
    monkeypatch.setattr(st, "form", lambda *_args, **_kwargs: nullcontext(), raising=False)
    monkeypatch.setattr(st, "title", lambda *_args, **_kwargs: None, raising=False)
    monkeypatch.setattr(st, "info", lambda *_args, **_kwargs: None, raising=False)
    monkeypatch.setattr(st, "error", lambda *_args, **_kwargs: None, raising=False)
    values = iter(["New-Test-Password-2026", "New-Test-Password-2026"])
    monkeypatch.setattr(st, "text_input", lambda *_args, **_kwargs: next(values), raising=False)
    monkeypatch.setattr(st, "form_submit_button", lambda *_args, **_kwargs: True, raising=False)

    class RerunCalled(Exception):
        pass

    monkeypatch.setattr(st, "rerun", lambda: (_ for _ in ()).throw(RerunCalled()), raising=False)

    with pytest.raises(RerunCalled):
        auth._render_password_recovery(st)

    assert updates == [("test-recovery-access", "New-Test-Password-2026")]
    assert auth._RECOVERY_STATE_KEY not in st.session_state
    assert auth.AUTH_SESSION_KEY not in st.session_state
    assert "SUPABASE_TEST_USER_A_PASSWORD" in st.session_state[auth._RECOVERY_SUCCESS_NOTICE_KEY]



def test_recovery_callback_component_captures_top_level_tokens_without_iframe_messaging():
    source = auth._RECOVERY_CALLBACK_COMPONENT_JS

    assert "window.location.hash" in source
    assert "window.location.search" in source
    assert 'params.get("type") === "recovery"' in source
    assert 'setTriggerValue("recovery_payload"' in source
    assert "window.history.replaceState" in source
    assert "window.parent" not in source
    assert "postMessage" not in source


def test_recovery_callback_component_result_is_returned_to_python(monkeypatch):
    from types import SimpleNamespace

    payload = {
        "status": "password_recovery",
        "recovery_id": "v2-callback-id",
        "access_token": "callback-access-token",
    }

    class FakeComponent:
        def __call__(self, **kwargs):
            assert callable(kwargs["on_recovery_payload_change"])
            return SimpleNamespace(recovery_payload=payload)

    monkeypatch.setattr(auth, "_RECOVERY_CALLBACK_COMPONENT", FakeComponent())

    result = auth._render_recovery_callback_component(
        FakeStreamlit(Fernet.generate_key().decode("ascii"))
    )

    assert result == payload


def test_recovery_callback_with_missing_access_token_shows_actionable_notice():
    st = FakeStreamlit(Fernet.generate_key().decode("ascii"))

    handled = auth._capture_password_recovery(st, {
        "status": "password_recovery_invalid",
        "message": "رابط الاستعادة وصل دون رمز جلسة صالح. اطلب رسالة استعادة جديدة.",
    })

    assert handled is True
    assert "اطلب رسالة استعادة جديدة" in st.session_state[auth._AUTH_NOTICE_KEY]


def test_browser_storage_component_no_longer_contains_recovery_message_bridge():
    component_path = Path(__file__).resolve().parents[1] / "supabase_browser_session_component" / "index.html"
    component = component_path.read_text(encoding="utf-8")

    assert "localStorage.getItem" in component
    assert "localStorage.setItem" in component
    assert "AI_COUNCIL_AUTH_BRIDGE_READY" not in component
    assert "AI_COUNCIL_RECOVERY_PAYLOAD" not in component
    assert "AI_COUNCIL_RECOVERY_ACK" not in component
    assert "PARENT_ORIGIN" not in component
