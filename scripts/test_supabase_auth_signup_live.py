#!/usr/bin/env python3
"""Live registration smoke test for two disposable Supabase Auth accounts.

All local configuration is validated for both users before any Auth request
is sent. This prevents partial account creation when one credential is invalid.
Only safe validator messages and outcome labels are written to CI logs; never
print passwords, tokens, API keys, or raw Auth responses.
"""
from __future__ import annotations

import os
import sys

from supabase_auth import (
    SupabaseAuthClient,
    SupabaseAuthError,
    _validate_project_url,
    _validate_publishable_key,
)


def required(name: str, *, strip: bool = True) -> str:
    value = os.environ.get(name, "")
    if not value.strip():
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip() if strip else value


def preflight() -> tuple[str, str, tuple[tuple[str, str, str], ...]] | None:
    """Validate every local input before the first network side effect."""
    raw_url = required("SUPABASE_URL")
    raw_key = required("SUPABASE_PUBLISHABLE_KEY")
    raw_users = (
        ("A", required("SUPABASE_TEST_USER_A_EMAIL"), required("SUPABASE_TEST_USER_A_PASSWORD", strip=False)),
        ("B", required("SUPABASE_TEST_USER_B_EMAIL"), required("SUPABASE_TEST_USER_B_PASSWORD", strip=False)),
    )
    errors: list[str] = []

    try:
        project_url = _validate_project_url(raw_url)
    except ValueError as exc:
        project_url = ""
        errors.append(f"SUPABASE_URL_INVALID: {exc}")

    try:
        publishable_key = _validate_publishable_key(raw_key)
    except ValueError as exc:
        publishable_key = ""
        errors.append(f"SUPABASE_PUBLISHABLE_KEY_INVALID: {exc}")

    normalized_users: list[tuple[str, str, str]] = []
    for label, raw_email, raw_password in raw_users:
        try:
            email = SupabaseAuthClient._normalized_email(raw_email)
        except ValueError as exc:
            errors.append(f"SUPABASE_TEST_USER_{label}_EMAIL_INVALID: {exc}")
            email = ""
        try:
            password = SupabaseAuthClient._validate_password(raw_password)
        except ValueError as exc:
            errors.append(f"SUPABASE_TEST_USER_{label}_PASSWORD_INVALID: {exc}")
            password = ""
        normalized_users.append((label, email, password))

    if normalized_users[0][1] and normalized_users[1][1] and (
        normalized_users[0][1].casefold() == normalized_users[1][1].casefold()
    ):
        errors.append("SUPABASE_TEST_USER_EMAILS_MUST_BE_DIFFERENT")

    if errors:
        print("LIVE_AUTH_SIGNUP=FAIL")
        for error in errors:
            # Validator messages above are fixed program text, never input values.
            print(f"LIVE_AUTH_SIGNUP_CONFIG_ERROR={error}")
        return None

    return project_url, publishable_key, tuple(normalized_users)


def main() -> int:
    config = preflight()
    if config is None:
        return 2
    project_url, publishable_key, users = config
    client = SupabaseAuthClient(
        supabase_url=project_url,
        publishable_key=publishable_key,
    )
    print("LIVE_AUTH_SIGNUP_PREFLIGHT=PASS")

    outcomes: list[str] = []
    failures: list[str] = []
    for label, email, password in users:
        try:
            session = client.sign_up(email, password)
        except SupabaseAuthError as signup_error:
            # Invalid email formatting is a configuration fault, not evidence
            # that the account already exists; do not send a redundant login.
            if "صيغة البريد الإلكتروني غير صالحة" in str(signup_error):
                failures.append(
                    f"{label}=SUPABASE_REJECTED_EMAIL_FORMAT; "
                    "update the corresponding email secret to a real valid address"
                )
                continue
            # A prior run may have created a valid disposable user. Try normal
            # password login; never use admin APIs or reveal supplied credentials.
            try:
                client.sign_in(email, password)
            except SupabaseAuthError as login_error:
                failures.append(
                    f"{label}=SIGNUP_AND_EXISTING_ACCOUNT_LOGIN_FAILED ({login_error})"
                )
            else:
                outcomes.append(f"{label}=EXISTING_ACCOUNT_LOGIN_VERIFIED")
            continue
        except ValueError as exc:
            # These should have been caught by preflight; keep the log useful and safe.
            failures.append(f"{label}=LOCAL_VALIDATION_FAILED ({exc})")
            continue

        if session is None:
            outcomes.append(
                f"{label}=SIGNUP_ACCEPTED_NO_SESSION_EMAIL_CONFIRMATION_MAY_BE_REQUIRED"
            )
        else:
            outcomes.append(f"{label}=SIGNUP_ACCEPTED_SESSION_IDENTITY_VERIFIED")

    if failures:
        for outcome in outcomes:
            print(f"LIVE_AUTH_SIGNUP_OUTCOME={outcome}")
        for failure in failures:
            print(f"LIVE_AUTH_SIGNUP_ACCOUNT_ERROR={failure}")
        print("LIVE_AUTH_SIGNUP=FAIL")
        return 1

    print("LIVE_AUTH_SIGNUP=PASS; " + "; ".join(outcomes))
    if any("NO_SESSION" in outcome for outcome in outcomes):
        print(
            "NEXT_STEP=Confirm both disposable email addresses if confirmation "
            "is enabled, then run phase auth-postgrest."
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SupabaseAuthError as exc:
        # SupabaseAuthError contains only an authored, user-safe message.
        print(f"LIVE_AUTH_SIGNUP=FAIL ({exc.__class__.__name__}: {exc})", file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        # Do not echo arbitrary exception text, which may include user input.
        print(f"LIVE_AUTH_SIGNUP=FAIL ({exc.__class__.__name__})", file=sys.stderr)
        raise SystemExit(1)
