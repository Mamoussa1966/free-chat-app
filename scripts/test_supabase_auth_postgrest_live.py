#!/usr/bin/env python3
"""Live Supabase Auth + PostgREST ownership test.

Run only against a dedicated test Supabase project with two confirmed,
disposable email/password accounts. The test logs in and refreshes both users,
creates one temporary canonical snapshot for A, proves B cannot read/update/
delete it, verifies the original is unchanged, and deletes the probe row.

Required environment variables (never commit these):
  SUPABASE_URL
  SUPABASE_PUBLISHABLE_KEY
  SUPABASE_TEST_USER_A_EMAIL
  SUPABASE_TEST_USER_A_PASSWORD
  SUPABASE_TEST_USER_B_EMAIL
  SUPABASE_TEST_USER_B_PASSWORD

This script deliberately does not create permanent Auth users: email confirmation
and account cleanup must be handled by the project owner, not bypassed.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid

import requests

from conversation_repository import AccountIdentity, OwnedConversationSnapshot
from supabase_auth import SupabaseAuthClient
from supabase_conversation_repository import SupabaseConversationRepository, _checksum


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def canonical_record(conversation_id: str) -> dict:
    session_id = f"auth-live-probe-{uuid.uuid4().hex}"
    message_id = f"message-{uuid.uuid4().hex}"
    request_id = f"request-{uuid.uuid4().hex}"
    round_id = f"{conversation_id}:{request_id}:r1"
    return {
        "conversation_id": conversation_id,
        "session_id": session_id,
        "canonical_store_contract": "V26_3_CANONICAL_CONVERSATION_STORE",
        "messages": [{
            "message_id": message_id,
            "conversation_id": conversation_id,
            "session_id": session_id,
            "role": "user",
            "request_id": request_id,
            "created_at": "2026-10-24T00:00:00Z",
            "content": "original-owner-A",
        }],
        "requests": [{
            "request_id": request_id,
            "conversation_id": conversation_id,
            "session_id": session_id,
            "message_id": message_id,
            "created_at": "2026-10-24T00:00:01Z",
            "state": "COMPLETED",
        }],
        "rounds": [{
            "round_id": round_id,
            "conversation_id": conversation_id,
            "session_id": session_id,
            "message_id": message_id,
            "request_id": request_id,
            "round": 1,
            "round_number": 1,
            "canonical_round_base": 1,
            "canonical_round_record_id": round_id,
            "canonical_identity_key": round_id,
            "created_at": "2026-10-24T00:00:02Z",
            "status": "COMPLETED",
        }],
    }


def assert_live(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)
    print(f"PASS — {message}")


def main() -> int:
    project_url = required("SUPABASE_URL")
    publishable_key = required("SUPABASE_PUBLISHABLE_KEY")
    email_a = required("SUPABASE_TEST_USER_A_EMAIL")
    password_a = required("SUPABASE_TEST_USER_A_PASSWORD")
    email_b = required("SUPABASE_TEST_USER_B_EMAIL")
    password_b = required("SUPABASE_TEST_USER_B_PASSWORD")

    auth = SupabaseAuthClient(supabase_url=project_url, publishable_key=publishable_key)
    session_a = auth.sign_in(email_a, password_a)
    session_b = auth.sign_in(email_b, password_b)
    assert_live(session_a.user_id != session_b.user_id, "Auth returns two distinct verified user identities")

    session_a = auth.refresh_session(session_a.refresh_token)
    session_b = auth.refresh_session(session_b.refresh_token)
    assert_live(session_a.user_id != session_b.user_id, "both users receive renewed, verified Auth sessions")

    owner_a = AccountIdentity(session_a.issuer, session_a.user_id)
    owner_b = AccountIdentity(session_b.issuer, session_b.user_id)
    repo_a = SupabaseConversationRepository(
        supabase_url=project_url,
        publishable_key=publishable_key,
        access_token=session_a.access_token,
        authenticated_identity=owner_a,
    )
    repo_b = SupabaseConversationRepository(
        supabase_url=project_url,
        publishable_key=publishable_key,
        access_token=session_b.access_token,
        authenticated_identity=owner_b,
    )

    conversation_id = f"auth-live-probe-{uuid.uuid4().hex}"
    record_a = canonical_record(conversation_id)
    snapshot_a = OwnedConversationSnapshot(owner_a, record_a)
    saved = False
    try:
        repo_a.save(snapshot_a)
        saved = True
        assert_live(
            repo_a.load(owner_a, conversation_id).canonical_record == record_a,
            "account A can save and read through authenticated PostgREST",
        )
        assert_live(
            repo_b.load(owner_b, conversation_id) is None,
            "account B cannot read account A's row",
        )
        assert_live(
            conversation_id not in repo_b.list_ids(owner_b),
            "account B cannot list account A's conversation",
        )
        assert_live(
            repo_b.delete(owner_b, conversation_id) is False,
            "account B cannot delete account A's row",
        )

        # Exercise the actual Data API PATCH path, not just adapter-side checks.
        patch_record = json.loads(json.dumps(record_a))
        patch_record["messages"][0]["content"] = "tampered-by-user-B"
        rest_url = project_url.rstrip("/") + "/rest/v1/council_conversations"
        headers_b = {
            "apikey": publishable_key,
            "Authorization": f"Bearer {session_b.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        patch = requests.Session().request(
            "PATCH",
            rest_url,
            params={"conversation_id": f"eq.{conversation_id}"},
            json={"canonical_record": patch_record, "checksum": _checksum(patch_record)},
            headers=headers_b,
            timeout=10,
        )
        assert_live(
            200 <= patch.status_code < 300 and patch.json() == [],
            "account B's direct PostgREST PATCH is filtered by RLS",
        )
        delete = requests.Session().request(
            "DELETE",
            rest_url,
            params={"conversation_id": f"eq.{conversation_id}"},
            headers=headers_b,
            timeout=10,
        )
        assert_live(
            200 <= delete.status_code < 300 and delete.json() == [],
            "account B's direct PostgREST DELETE is filtered by RLS",
        )
        after = repo_a.load(owner_a, conversation_id)
        assert_live(
            after is not None and after.canonical_record["messages"][0]["content"] == "original-owner-A",
            "account A's canonical record stays unchanged after B's direct API attempts",
        )
    finally:
        if saved:
            assert_live(repo_a.delete(owner_a, conversation_id), "temporary conversation probe row was removed")
    print("LIVE_AUTH_POSTGREST_RLS=PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Never echo credentials, access/refresh tokens, or raw HTTP response bodies.
        print(f"LIVE_AUTH_POSTGREST_RLS=FAIL ({exc.__class__.__name__})", file=sys.stderr)
        raise SystemExit(1)
