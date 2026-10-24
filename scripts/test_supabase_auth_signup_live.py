#!/usr/bin/env python3
"""Live registration smoke test for two disposable Supabase Auth accounts.

Use only fresh addresses controlled by the project owner, in the dedicated
ai-council-storage-test project. If email confirmation is enabled, this tests
the real signup endpoint and reports that confirmation is needed; click those
emails, then run the login/refresh/PostgREST acceptance workflow.

The script never prints passwords, tokens, or raw Auth response bodies. It does
not create or use a service-role/admin key. Auth test accounts remain until the
owner removes them from the dedicated project.
"""
from __future__ import annotations

import os
import sys

from supabase_auth import SupabaseAuthClient, SupabaseAuthError


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def main() -> int:
    client = SupabaseAuthClient(
        supabase_url=required("SUPABASE_URL"),
        publishable_key=required("SUPABASE_PUBLISHABLE_KEY"),
    )
    users = (
        ("A", required("SUPABASE_TEST_USER_A_EMAIL"), required("SUPABASE_TEST_USER_A_PASSWORD")),
        ("B", required("SUPABASE_TEST_USER_B_EMAIL"), required("SUPABASE_TEST_USER_B_PASSWORD")),
    )
    if users[0][1].casefold() == users[1][1].casefold():
        raise RuntimeError("Test accounts A and B must use different email addresses")

    outcomes = []
    for label, email, password in users:
        session = client.sign_up(email, password)
        if session is None:
            outcomes.append(f"{label}=SIGNUP_ACCEPTED_NO_SESSION_EMAIL_CONFIRMATION_MAY_BE_REQUIRED")
        else:
            outcomes.append(f"{label}=SIGNUP_ACCEPTED_SESSION_ISSUED_IDENTITY_VERIFIED")
    print("LIVE_AUTH_SIGNUP=PASS; " + "; ".join(outcomes))
    if any("NO_SESSION" in outcome for outcome in outcomes):
        print("NEXT_STEP=Confirm both disposable email addresses, then run phase auth-postgrest.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SupabaseAuthError as exc:
        # SupabaseAuthError contains only a user-safe message, never raw response data.
        print(f"LIVE_AUTH_SIGNUP=FAIL ({exc.__class__.__name__}: {exc})", file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        print(f"LIVE_AUTH_SIGNUP=FAIL ({exc.__class__.__name__})", file=sys.stderr)
        raise SystemExit(1)
