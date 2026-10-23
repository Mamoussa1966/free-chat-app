"""Additional validation gates for snapshot referential integrity and immutability."""
from __future__ import annotations

import copy

import pytest

from conversation_file_repository import FileConversationRepository
from conversation_repository import (
    CANONICAL_STORE_CONTRACT,
    AccountIdentity,
    ConversationIdentityConflict,
    OwnedConversationSnapshot,
)

OWNER = AccountIdentity("https://identity.example.test", "subject-integrity")


def canonical_record():
    return {
        "conversation_id": "integrity-conversation",
        "session_id": "session-1",
        "canonical_store_contract": CANONICAL_STORE_CONTRACT,
        "messages": [{
            "message_id": "message-1",
            "conversation_id": "integrity-conversation",
            "session_id": "session-1",
            "role": "user",
            "request_id": "request-1",
            "created_at": "2026-10-23T00:00:00Z",
        }],
        "requests": [{
            "request_id": "request-1",
            "conversation_id": "integrity-conversation",
            "session_id": "session-1",
            "message_id": "message-1",
            "created_at": "2026-10-23T00:00:01Z",
            "state": "COMPLETED",
        }],
        "rounds": [{
            "round_id": "integrity-conversation:request-1:r1",
            "conversation_id": "integrity-conversation",
            "session_id": "session-1",
            "message_id": "message-1",
            "request_id": "request-1",
            "round": 1,
            "round_number": 1,
            "ordinal": 1,
            "canonical_round_base": 1,
            "canonical_round_record_id": "integrity-conversation:request-1:r1",
            "canonical_identity_key": "integrity-conversation:request-1:r1",
            "created_at": "2026-10-23T00:00:02Z",
            "status": "COMPLETED",
        }],
    }


@pytest.mark.parametrize("collection", ["messages", "requests", "rounds"])
def test_snapshot_rejects_rows_from_a_different_conversation(collection):
    record = canonical_record()
    record[collection][0]["conversation_id"] = "another-conversation"
    with pytest.raises(ValueError, match="another conversation"):
        OwnedConversationSnapshot(OWNER, record)


def test_snapshot_rejects_user_message_with_dangling_request_reference():
    record = canonical_record()
    record["messages"][0]["request_id"] = "missing-request"
    with pytest.raises(ValueError, match="missing request"):
        OwnedConversationSnapshot(OWNER, record)


def test_snapshot_rejects_request_with_dangling_message_reference():
    record = canonical_record()
    record["requests"][0]["message_id"] = "missing-message"
    with pytest.raises(ValueError, match="missing message"):
        OwnedConversationSnapshot(OWNER, record)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("request_id", "missing-request", "missing request"),
        ("message_id", "missing-message", "missing message"),
    ],
)
def test_snapshot_rejects_round_with_dangling_identity_reference(field, value, message):
    record = canonical_record()
    record["rounds"][0][field] = value
    with pytest.raises(ValueError, match=message):
        OwnedConversationSnapshot(OWNER, record)


def test_snapshot_rejects_contradictory_request_and_user_message_binding():
    record = canonical_record()
    record["messages"].append({
        "message_id": "message-2",
        "conversation_id": "integrity-conversation",
        "session_id": "session-1",
        "role": "assistant",
        "created_at": "2026-10-23T00:00:03Z",
    })
    record["requests"][0]["message_id"] = "message-2"
    with pytest.raises(ValueError, match="message/request binding mismatch"):
        OwnedConversationSnapshot(OWNER, record)


def test_file_adapter_refuses_rewrite_of_existing_round_identity_alias(tmp_path):
    repository = FileConversationRepository(tmp_path / "store")
    original = canonical_record()
    repository.save(OwnedConversationSnapshot(OWNER, original))

    changed = copy.deepcopy(original)
    changed["rounds"][0]["round_number"] = 9
    # Leave the primary round field unchanged; the duplicated canonical alias
    # must not be allowed to disagree with the stored identity.
    changed["rounds"][0]["round"] = 1
    with pytest.raises(ConversationIdentityConflict, match="identity binding"):
        repository.save(OwnedConversationSnapshot(OWNER, changed))

    restored = repository.load(OWNER, original["conversation_id"])
    assert restored is not None
    assert restored.canonical_record["rounds"][0]["round_number"] == 1
