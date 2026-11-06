from __future__ import annotations

import copy
import json

import pytest

from backup_engine import build_conversation_backup
from backup_restore import (
    BackupRestoreError,
    build_restore_snapshots,
    restore_only_missing_conversations,
)
from conversation_repository import AccountIdentity, OwnedConversationSnapshot


OWNER = AccountIdentity(
    "https://restore-test.supabase.co/auth/v1",
    "00000000-0000-4000-8000-000000000001",
)


def _chat(conversation_id: str = "restore-conversation-1") -> dict:
    message = {
        "message_id": "message-1",
        "conversation_id": conversation_id,
        "session_id": "session-1",
        "role": "user",
        "request_id": "request-1",
        "created_at": "2026-11-06T00:00:00Z",
        "content": "canonical user text",
    }
    request = {
        "request_id": "request-1",
        "conversation_id": conversation_id,
        "session_id": "session-1",
        "message_id": "message-1",
        "created_at": "2026-11-06T00:00:00Z",
        "state": "COMPLETED",
    }
    round_row = {
        "round_id": "round-1",
        "conversation_id": conversation_id,
        "session_id": "session-1",
        "message_id": "message-1",
        "request_id": "request-1",
        "round": 1,
        "created_at": "2026-11-06T00:00:01Z",
        "status": "COMPLETED",
    }
    record = {
        "conversation_id": conversation_id,
        "session_id": "session-1",
        "canonical_store_contract": "V26_3_CANONICAL_CONVERSATION_STORE",
        "canonical_store_committed": True,
        "messages": [message],
        "requests": [request],
        "rounds": [round_row],
    }
    return {
        "id": conversation_id,
        "conversation_id": conversation_id,
        "session_id": "session-1",
        "title": "Restore test",
        "created_at": "2026-11-06T00:00:00Z",
        "messages": [{"role": "user", "content": "canonical user text"}],
        "conversation_record": record,
        "message_ledger_v24": [message],
        "request_ledger_v24": [request],
        "round_ledger_v24": [round_row],
        "bridge_ledger_v24": [],
        "request_records": [{"request_id": "request-1"}],
        "request_ids": ["request-1"],
        "history_identity_ledger": [{"message_id": "message-1"}],
        "result_keys": ["request-1:gemini"],
    }


class InsertOnlyRepository:
    def __init__(self, owner: AccountIdentity):
        self.owner = owner
        self.rows: dict[str, OwnedConversationSnapshot] = {}
        self.insert_calls = 0

    def restore_if_absent(self, snapshot: OwnedConversationSnapshot) -> bool:
        if snapshot.owner != self.owner:
            raise AssertionError("foreign owner was passed to repository")
        self.insert_calls += 1
        if snapshot.conversation_id in self.rows:
            return False
        self.rows[snapshot.conversation_id] = snapshot
        return True


def test_restore_builder_validates_bundle_and_preserves_canonical_identity():
    document = build_conversation_backup(
        [_chat()],
        source="test",
        exported_at="2026-11-06T11:00:00Z",
    )
    before = copy.deepcopy(document)

    snapshots = build_restore_snapshots(document, OWNER)

    assert len(snapshots) == 1
    assert snapshots[0].owner == OWNER
    assert snapshots[0].conversation_id == "restore-conversation-1"
    record = snapshots[0].canonical_record
    assert record["canonical_store_contract"] == "V26_3_CANONICAL_CONVERSATION_STORE"
    assert record["messages"][0]["message_id"] == "message-1"
    assert record["requests"][0]["request_id"] == "request-1"
    assert record["rounds"][0]["round_id"] == "round-1"
    assert record["_streamlit_state"]["title"] == "Restore test"
    assert record["_streamlit_state"]["result_keys"] == ["request-1:gemini"]
    assert document == before


def test_restore_rejects_tampering_before_any_repository_write():
    document = build_conversation_backup([_chat()])
    document["conversations"][0]["snapshot"]["canonical_conversation_record"]["messages"][0]["content"] = "tampered"
    repository = InsertOnlyRepository(OWNER)

    with pytest.raises(BackupRestoreError, match="integrity"):
        restore_only_missing_conversations(
            document,
            owner=OWNER,
            repository=repository,
        )

    assert repository.insert_calls == 0
    assert repository.rows == {}


def test_restore_inserts_only_missing_conversations_and_skips_existing_without_overwrite():
    first = _chat("restore-existing")
    second = _chat("restore-new")
    document = build_conversation_backup([first, second])
    repository = InsertOnlyRepository(OWNER)

    # Seed a pre-existing conversation with different text. Restore must skip it.
    existing_record = copy.deepcopy(first["conversation_record"])
    existing_record["messages"][0]["content"] = "existing live content"
    existing = OwnedConversationSnapshot(OWNER, existing_record)
    repository.rows[existing.conversation_id] = existing

    result = restore_only_missing_conversations(
        document,
        owner=OWNER,
        repository=repository,
    )

    assert result["status"] == "COMPLETED"
    assert result["total"] == 2
    assert result["restored"] == 1
    assert result["skipped_existing"] == 1
    assert result["existing_conversations_overwritten"] == 0
    assert repository.rows["restore-existing"].canonical_record["messages"][0]["content"] == "existing live content"
    assert repository.rows["restore-new"].canonical_record["messages"][0]["content"] == "canonical user text"


def test_restore_requires_atomic_insert_only_repository_method():
    document = build_conversation_backup([_chat()])
    with pytest.raises(BackupRestoreError, match="atomic insert-only"):
        restore_only_missing_conversations(
            document,
            owner=OWNER,
            repository=object(),
        )


def test_restore_requires_a_verified_account_identity():
    document = build_conversation_backup([_chat()])
    with pytest.raises(BackupRestoreError, match="authenticated owner"):
        build_restore_snapshots(document, object())
