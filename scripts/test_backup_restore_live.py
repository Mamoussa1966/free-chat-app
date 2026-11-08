#!/usr/bin/env python3
"""Live, isolated Supabase conversation restore acceptance test.

Uses two already-confirmed disposable Auth accounts and is pinned to the
ai-council-storage-test project. It never calls an AI provider and always
attempts to delete only the synthetic rows it creates.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

from backup_engine import build_conversation_backup
from backup_restore import restore_only_missing_conversations
from conversation_repository import (
    AccountIdentity,
    ConversationRepositoryError,
    OwnedConversationSnapshot,
)
from supabase_auth import SupabaseAuthClient
from supabase_conversation_repository import SupabaseConversationRepository


EXPECTED_TEST_HOST = "pidcepvwsezdrlhxqksg.supabase.co"
CANONICAL_CONTRACT = "V26_3_CANONICAL_CONVERSATION_STORE"


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def assert_live(condition: bool, label: str) -> None:
    if not condition:
        raise RuntimeError(label)
    print(f"PASS — {label}")


def make_record(conversation_id: str, content: str) -> dict:
    session_id = f"restore-live-session-{uuid.uuid4().hex}"
    message_id = f"restore-live-message-{uuid.uuid4().hex}"
    request_id = f"restore-live-request-{uuid.uuid4().hex}"
    round_id = f"{conversation_id}:{request_id}:r1"
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    message = {
        "message_id": message_id,
        "conversation_id": conversation_id,
        "session_id": session_id,
        "role": "user",
        "request_id": request_id,
        "created_at": timestamp,
        "content": content,
    }
    request = {
        "request_id": request_id,
        "conversation_id": conversation_id,
        "session_id": session_id,
        "message_id": message_id,
        "created_at": timestamp,
        "state": "COMPLETED",
    }
    round_row = {
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
        "created_at": timestamp,
        "status": "COMPLETED",
    }
    return {
        "conversation_id": conversation_id,
        "session_id": session_id,
        "canonical_store_contract": CANONICAL_CONTRACT,
        "canonical_store_committed": True,
        "messages": [message],
        "requests": [request],
        "rounds": [round_row],
    }


def make_export_chat(conversation_id: str, content: str) -> dict:
    record = make_record(conversation_id, content)
    return {
        "conversation_id": conversation_id,
        "session_id": record["session_id"],
        "title": "Disposable live restore acceptance",
        "created_at": record["messages"][0]["created_at"],
        "messages": [{"role": "user", "content": content}],
        "conversation_record": record,
        "message_ledger_v24": record["messages"],
        "request_ledger_v24": record["requests"],
        "round_ledger_v24": record["rounds"],
        "bridge_ledger_v24": [],
        "request_records": [{"request_id": record["requests"][0]["request_id"]}],
        "request_ids": [record["requests"][0]["request_id"]],
        "history_identity_ledger": [{"message_id": record["messages"][0]["message_id"]}],
        "result_keys": [],
        "_backup_presentation_state": {
            "title": "Disposable live restore acceptance",
            "created_at": record["messages"][0]["created_at"],
            "messages": [{"role": "user", "content": content}],
            "request_records": [{"request_id": record["requests"][0]["request_id"]}],
            "request_ids": [record["requests"][0]["request_id"]],
            "history_identity_ledger": [{"message_id": record["messages"][0]["message_id"]}],
            "result_keys": [],
            "bridge_ledger_v24": [],
        },
    }


def main() -> int:
    project_url = required("SUPABASE_URL").rstrip("/")
    publishable_key = required("SUPABASE_PUBLISHABLE_KEY")
    email_a = required("SUPABASE_TEST_USER_A_EMAIL")
    password_a = required("SUPABASE_TEST_USER_A_PASSWORD")
    email_b = required("SUPABASE_TEST_USER_B_EMAIL")
    password_b = required("SUPABASE_TEST_USER_B_PASSWORD")

    parsed = urlsplit(project_url)
    # Fail closed before authentication or writes if the configured secret
    # points anywhere other than the explicitly authorized test project.
    assert_live(
        parsed.scheme == "https"
        and parsed.netloc.lower() == EXPECTED_TEST_HOST
        and parsed.path in ("", "/")
        and not parsed.query
        and not parsed.fragment,
        "configured Supabase URL is pinned to the dedicated test project",
    )

    auth = SupabaseAuthClient(
        supabase_url=project_url,
        publishable_key=publishable_key,
    )
    session_a = auth.sign_in(email_a, password_a)
    session_b = auth.sign_in(email_b, password_b)
    assert_live(
        session_a.user_id != session_b.user_id,
        "two distinct disposable Auth accounts signed in successfully",
    )

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

    existing_id = f"restore-live-existing-{uuid.uuid4().hex}"
    missing_id = f"restore-live-missing-{uuid.uuid4().hex}"
    seeded = False
    created_ids: list[str] = []

    try:
        original_existing = make_record(existing_id, "original-owner-A-content")
        repo_a.save(OwnedConversationSnapshot(owner_a, original_existing))
        seeded = True
        created_ids.append(existing_id)
        assert_live(
            repo_a.load(owner_a, existing_id).canonical_record == original_existing,
            "account A seeded one disposable pre-existing conversation",
        )

        # The backup deliberately carries changed content for the existing ID
        # plus a different ID which is absent from the target account.
        document = build_conversation_backup(
            [
                make_export_chat(existing_id, "backup-attempted-overwrite"),
                make_export_chat(missing_id, "backup-new-missing-conversation"),
            ],
            source="live_restore_acceptance_test_project",
        )
        result = restore_only_missing_conversations(
            document,
            owner=owner_a,
            repository=repo_a,
        )
        assert_live(
            result["status"] == "COMPLETED"
            and result["total"] == 2
            and result["restored"] == 1
            and result["skipped_existing"] == 1
            and result["existing_conversations_overwritten"] == 0
            and result["writes_are_insert_only"] is True
            and result["provider_api_calls"] == 0,
            "restore inserted exactly one missing ID and skipped the existing ID",
        )
        created_ids.extend(result["restored_conversation_ids"])

        stored_existing = repo_a.load(owner_a, existing_id)
        stored_missing = repo_a.load(owner_a, missing_id)
        assert_live(
            stored_existing is not None
            and stored_existing.canonical_record["messages"][0]["content"] == "original-owner-A-content",
            "same-owner existing conversation was not overwritten",
        )
        assert_live(
            stored_missing is not None
            and stored_missing.canonical_record["messages"][0]["content"] == "backup-new-missing-conversation",
            "missing conversation was inserted with its canonical history",
        )

        repeated = restore_only_missing_conversations(
            document,
            owner=owner_a,
            repository=repo_a,
        )
        assert_live(
            repeated["status"] == "COMPLETED"
            and repeated["restored"] == 0
            and repeated["skipped_existing"] == 2
            and repeated["existing_conversations_overwritten"] == 0,
            "repeat restore is idempotent and skips both existing IDs",
        )

        assert_live(
            repo_b.load(owner_b, existing_id) is None
            and repo_b.load(owner_b, missing_id) is None
            and existing_id not in repo_b.list_ids(owner_b)
            and missing_id not in repo_b.list_ids(owner_b),
            "account B cannot read or list account A's restored records",
        )
        assert_live(
            repo_b.delete(owner_b, existing_id) is False
            and repo_b.delete(owner_b, missing_id) is False,
            "account B cannot delete account A's restored records",
        )

        # Attempt a conflicting restore under B's own verified identity.
        # The primary-key collision must fail closed; RLS must hide A's row.
        foreign_attempt = OwnedConversationSnapshot(
            owner_b,
            make_record(existing_id, "account-B-must-not-overwrite-account-A"),
        )
        blocked = False
        try:
            repo_b.restore_if_absent(foreign_attempt)
        except ConversationRepositoryError:
            blocked = True
        assert_live(
            blocked,
            "account B cannot restore over account A's existing conversation ID",
        )

        after_foreign_attempt = repo_a.load(owner_a, existing_id)
        assert_live(
            after_foreign_attempt is not None
            and after_foreign_attempt.canonical_record["messages"][0]["content"] == "original-owner-A-content",
            "account A's original content remains unchanged after account B's attempt",
        )
    finally:
        # Remove only the unique synthetic rows created by this test, using A's
        # authenticated owner-scoped repository. Never touch other IDs.
        if seeded:
            for conversation_id in reversed(created_ids):
                repo_a.delete(owner_a, conversation_id)
            assert_live(
                repo_a.load(owner_a, existing_id) is None
                and repo_a.load(owner_a, missing_id) is None,
                "all synthetic test conversations were removed",
            )

    print("LIVE_BACKUP_RESTORE_ACCEPTANCE=PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Never echo credentials, tokens, conversation payloads, or HTTP bodies.
        print(
            f"LIVE_BACKUP_RESTORE_ACCEPTANCE=FAIL ({exc.__class__.__name__})",
            file=sys.stderr,
        )
        raise SystemExit(1)
