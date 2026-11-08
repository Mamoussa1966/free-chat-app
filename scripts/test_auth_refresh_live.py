#!/usr/bin/env python3
"""Live, test-project-only Supabase Auth refresh-token acceptance test.

Exercises the actual Streamlit session restore path for two pre-authorized
disposable Auth accounts. It creates/revokes only Auth sessions; it never
reads/writes conversation rows, changes passwords, or calls AI providers.
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
from urllib.parse import urlsplit

import requests

from supabase_auth import SupabaseAuthClient, SupabaseAuthError


EXPECTED_TEST_HOST = "pidcepvwsezdrlhxqksg.supabase.co"
EXPECTED_TEST_PUBLISHABLE_KEY_SHA256 = (
    "4466db377d54ad52d16b78002fa97e0cadfff82cd3691b143ecd93ffb0377b32"
)
EXPECTED_EMAIL_FINGERPRINTS = {
    "A": "f6cfaac879514b2d2f5ace8c2fe076d14c08639d669d40eb2f8cf3af87273d31",
    "B": "6c53ece92c5e1dcbe3785e183b66ee39f96e61f9b10ff8b4ee497baa54ae3e68",
}


class StatusOnlyTransport:
    """HTTP transport that retains only the most recent status code."""

    def __init__(self) -> None:
        self._session = requests.Session()
        self.last_status: int | None = None

    def request(self, *args, **kwargs):
        self.last_status = None
        response = self._session.request(*args, **kwargs)
        self.last_status = int(getattr(response, "status_code", 0) or 0)
        return response


def required(name: str, *, strip: bool = True) -> str:
    value = os.environ.get(name, "")
    if not value.strip():
        raise RuntimeError(f"missing required configuration: {name}")
    return value.strip() if strip else value


def check(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def assert_test_project(project_url: str, publishable_key: str) -> None:
    parsed = urlsplit(project_url)
    check(
        parsed.scheme == "https"
        and parsed.netloc.lower() == EXPECTED_TEST_HOST
        and parsed.path in ("", "/")
        and not parsed.query
        and not parsed.fragment,
        "test project URL is not the pinned dedicated test project",
    )
    key_fingerprint = hashlib.sha256(publishable_key.encode("utf-8")).hexdigest()
    check(
        key_fingerprint == EXPECTED_TEST_PUBLISHABLE_KEY_SHA256,
        "publishable key does not match the pinned test project",
    )


def assert_identity(label: str, original, renewed, previous_refresh_token: str) -> None:
    check(renewed.user_id == original.user_id, f"account {label} identity changed during refresh")
    check(renewed.issuer == original.issuer, f"account {label} issuer changed during refresh")
    check(bool(renewed.access_token), f"account {label} renewed access token is missing")
    check(bool(renewed.refresh_token), f"account {label} renewed refresh token is missing")
    check(
        renewed.refresh_token != previous_refresh_token,
        f"account {label} refresh token did not rotate",
    )
    check(renewed.expires_at > int(time.time()), f"account {label} renewed access token is expired")


def main() -> int:
    project_url = required("SUPABASE_URL").rstrip("/")
    publishable_key = required("SUPABASE_PUBLISHABLE_KEY")
    accounts = {
        "A": (
            required("SUPABASE_TEST_USER_A_EMAIL"),
            required("SUPABASE_TEST_USER_A_PASSWORD", strip=False),
        ),
        "B": (
            required("SUPABASE_TEST_USER_B_EMAIL"),
            required("SUPABASE_TEST_USER_B_PASSWORD", strip=False),
        ),
    }

    for label, (email, _password) in accounts.items():
        fingerprint = hashlib.sha256(email.strip().casefold().encode("utf-8")).hexdigest()
        check(
            fingerprint == EXPECTED_EMAIL_FINGERPRINTS[label],
            f"account {label} email does not match its allowlisted disposable test identity",
        )
        print(f"AUTH_ACCOUNT_{label}_IDENTITY_PIN=PASS")

    assert_test_project(project_url, publishable_key)
    print("AUTH_REFRESH_TARGET=PASS; pinned dedicated test project only")

    transport = StatusOnlyTransport()
    auth = SupabaseAuthClient(
        supabase_url=project_url,
        publishable_key=publishable_key,
        session=transport,
    )
    active_sessions = {}
    user_ids = {}
    failures = []

    try:
        for label, (email, password) in accounts.items():
            try:
                initial = auth.sign_in(email, password)
                active_sessions[label] = initial
                user_ids[label] = initial.user_id
                print(f"AUTH_ACCOUNT_{label}_SIGN_IN=PASS")

                # Exercise the same code path used when Streamlit restores a
                # session whose access JWT has expired or is within 90 seconds
                # of expiry. This changes only this local in-memory snapshot.
                expired_state = initial.to_state()
                expired_state["expires_at"] = int(time.time()) - 1
                restored = auth.restore_or_refresh(expired_state)
                active_sessions[label] = restored
                assert_identity(label, initial, restored, initial.refresh_token)
                print(f"AUTH_ACCOUNT_{label}_RESTORE_REFRESH=PASS")

                # Prove the newly rotated refresh token is itself usable,
                # without reusing the old token or triggering reuse detection.
                chained = auth.refresh_session(restored.refresh_token)
                active_sessions[label] = chained
                assert_identity(label, initial, chained, restored.refresh_token)
                print(f"AUTH_ACCOUNT_{label}_REFRESH_CHAIN=PASS")

            except Exception as exc:
                failures.append(label)
                status = transport.last_status
                status_label = str(status) if status is not None else "unknown"
                print(
                    f"AUTH_ACCOUNT_{label}_REFRESH=FAIL; "
                    f"error_type={type(exc).__name__}; http_status={status_label}",
                    file=sys.stderr,
                )

        if len(user_ids) == 2:
            check(user_ids["A"] != user_ids["B"], "test accounts did not resolve to distinct Auth users")
            print("AUTH_REFRESH_TWO_ACCOUNT_IDENTITY_ISOLATION=PASS")

    finally:
        cleanup_failures = []
        for label, session in reversed(list(active_sessions.items())):
            try:
                auth.sign_out(session.access_token)
                print(f"AUTH_ACCOUNT_{label}_SESSION_CLEANUP=PASS")
            except Exception as exc:
                cleanup_failures.append(label)
                print(
                    f"AUTH_ACCOUNT_{label}_SESSION_CLEANUP=FAIL; "
                    f"error_type={type(exc).__name__}",
                    file=sys.stderr,
                )

    if failures or cleanup_failures:
        print("LIVE_AUTH_REFRESH_ACCEPTANCE=FAIL", file=sys.stderr)
        return 1

    if len(user_ids) != 2:
        print("LIVE_AUTH_REFRESH_ACCEPTANCE=FAIL; both accounts were not tested", file=sys.stderr)
        return 1

    print("LIVE_AUTH_REFRESH_ACCEPTANCE=PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Never print passwords, email addresses, tokens, payloads or raw HTTP bodies.
        print(
            f"LIVE_AUTH_REFRESH_ACCEPTANCE=FAIL; error_type={type(exc).__name__}",
            file=sys.stderr,
        )
        raise SystemExit(1)
