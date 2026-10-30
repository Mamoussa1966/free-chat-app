#!/usr/bin/env python3
"""Request user-scoped password recovery emails for the two allowlisted test users.

This script only calls the public Supabase Auth recovery endpoint. It does not
change passwords, access Auth admin APIs, or print email addresses or tokens.
"""
from __future__ import annotations

import hashlib
import os
import sys

import requests


EXPECTED_URL = "https://pidcepvwsezdrlhxqksg.supabase.co"
RECOVERY_REDIRECT_URL = "https://free-chat-app-qmqyxzh2oe2n3qwcvqvpdh.streamlit.app/"
EXPECTED_EMAIL_FINGERPRINTS = {
    "A": "f6cfaac879514b2d2f5ace8c2fe076d14c08639d669d40eb2f8cf3af87273d31",
    "B": "6c53ece92c5e1dcbe3785e183b66ee39f96e61f9b10ff8b4ee497baa54ae3e68",
}


def required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value.strip():
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip()


def main() -> int:
    project_url = required("SUPABASE_URL").rstrip("/")
    publishable_key = required("SUPABASE_PUBLISHABLE_KEY")
    if project_url != EXPECTED_URL:
        print("LIVE_AUTH_RECOVERY_REQUEST=BLOCKED; wrong Supabase test project")
        return 2

    users = {
        "A": required("SUPABASE_TEST_USER_A_EMAIL").strip(),
        "B": required("SUPABASE_TEST_USER_B_EMAIL").strip(),
    }
    normalized = {label: email.casefold() for label, email in users.items()}
    if normalized["A"] == normalized["B"]:
        print("LIVE_AUTH_RECOVERY_REQUEST=BLOCKED; test identities are not distinct")
        return 2

    for label, email in normalized.items():
        fingerprint = hashlib.sha256(email.encode("utf-8")).hexdigest()
        if fingerprint != EXPECTED_EMAIL_FINGERPRINTS[label]:
            print(f"LIVE_AUTH_RECOVERY_EMAIL_{label}_MATCH=FAIL")
            return 2
        print(f"LIVE_AUTH_RECOVERY_EMAIL_{label}_MATCH=PASS")

    failures = 0
    endpoint = project_url + "/auth/v1/recover"
    headers = {
        "apikey": publishable_key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    with requests.Session() as session:
        for label in ("A", "B"):
            try:
                response = session.post(
                    endpoint,
                    params={"redirect_to": RECOVERY_REDIRECT_URL},
                    json={"email": users[label]},
                    headers=headers,
                    timeout=15,
                )
            except requests.RequestException:
                print(f"LIVE_AUTH_RECOVERY_REQUEST_{label}=NETWORK_ERROR")
                failures += 1
                continue

            if 200 <= response.status_code < 300:
                print(f"LIVE_AUTH_RECOVERY_REQUEST_{label}=ACCEPTED")
            else:
                # Never print the response body: it can contain user-specific data.
                print(f"LIVE_AUTH_RECOVERY_REQUEST_{label}=FAIL (HTTP {response.status_code})")
                failures += 1

    if failures:
        print("LIVE_AUTH_RECOVERY_REQUEST=FAIL")
        return 1

    print("LIVE_AUTH_RECOVERY_REQUEST=PASS; both requests were accepted by test Auth")
    print("NEXT_STEP=Open each Supabase recovery email, set a new password in the AI Council recovery form, then update the matching GitHub Actions password Secret.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"LIVE_AUTH_RECOVERY_REQUEST=FAIL ({exc.__class__.__name__})", file=sys.stderr)
        raise SystemExit(1)
