"""Security and durability-contract tests for the local file adapter.

These tests use a temporary directory only. They do not make the adapter a
production database and do not wire it into the Streamlit application.
"""
from __future__ import annotations

import copy
import json
import os

import pytest

from conversation_file_repository import (
    FILE_REPOSITORY_SCHEMA,
    FileConversationRepository,
)
from conversation_repository import (
    CANONICAL_STORE_CONTRACT,
    AccountIdentity,
    ConversationIdentityConflict,
    ConversationOwnershipError,
    ConversationRepository,
    ConversationRepositoryError,
    OwnedConversationSnapshot,
)


OWNER_A = AccountIdentity("https://identity.example.test", "subject-A")
OWNER_B = AccountIdentity("https://identity.example.test", "subject-B")


def canonical_record(conversation_id="conversation / private ID", message_id="message-1"):
    request_id = f"request-{message_id}"
    round_id = f"{conversation_id}:{request_id}:round-1"
    return {
        "conversation_id": conversation_id,
        "session_id": "session-1",
        "canonical_store_contract": CANONICAL_STORE_CONTRACT,
        "messages": [{
            "message_id": message_id,
            "conversation_id": conversation_id,
            "session_id": "session-1",
            "role": "user",
            "request_id": request_id,
            "created_at": "2026-10-23T00:00:00Z",
            "content": "private test message",
        }],
        "requests": [{
            "request_id": request_id,
            "conversation_id": conversation_id,
            "session_id": "session-1",
            "message_id": message_id,
            "state": "COMPLETED",
        }],
        "rounds": [{
            "round_id": round_id,
            "conversation_id": conversation_id,
            "session_id": "session-1",
            "message_id": message_id,
            "request_id": request_id,
            "round": 1,
            "status": "COMPLETED",
        }],
    }


@pytest.fixture
def repository(tmp_path):
    return FileConversationRepository(tmp_path / "private-conversation-store")


def snapshot(owner=OWNER_A, record=None):
    return OwnedConversationSnapshot(owner, record or canonical_record())


def test_adapter_implements_repository_protocol_and_reloads_in_new_instance(tmp_path):
    data_dir = tmp_path / "persisted"
    first = FileConversationRepository(data_dir)
    candidate = snapshot()
    assert isinstance(first, ConversationRepository)

    first.save(candidate)
    second = FileConversationRepository(data_dir)
    restored = second.load(OWNER_A, candidate.conversation_id)

    assert restored is not None
    assert restored.owner == OWNER_A
    assert restored.canonical_record == candidate.canonical_record


def test_owner_isolation_applies_to_load_list_save_and_delete(repository):
    candidate = snapshot()
    repository.save(candidate)

    assert repository.load(OWNER_A, candidate.conversation_id) is not None
    assert repository.load(OWNER_B, candidate.conversation_id) is None
    assert repository.list_ids(OWNER_A) == [candidate.conversation_id]
    assert repository.list_ids(OWNER_B) == []
    assert repository.delete(OWNER_B, candidate.conversation_id) is False
    assert repository.load(OWNER_A, candidate.conversation_id) is not None

    with pytest.raises(ConversationOwnershipError):
        repository.save(snapshot(OWNER_B, candidate.canonical_record))

    assert repository.delete(OWNER_A, candidate.conversation_id) is True
    assert repository.load(OWNER_A, candidate.conversation_id) is None


def test_unchanged_save_is_idempotent_and_does_not_rewrite_file(repository):
    candidate = snapshot()
    repository.save(candidate)
    path = repository._path_for(candidate.conversation_id)
    before = path.read_bytes()
    before_mtime = path.stat().st_mtime_ns

    repository.save(candidate)

    assert path.read_bytes() == before
    assert path.stat().st_mtime_ns == before_mtime


def test_adapter_preserves_immutable_identity_and_rejects_history_loss(repository):
    original = canonical_record()
    repository.save(snapshot(record=original))
    path = repository._path_for(original["conversation_id"])
    before = path.read_bytes()

    rewritten = copy.deepcopy(original)
    rewritten["messages"][0]["request_id"] = "request-tampered"
    with pytest.raises(ConversationIdentityConflict):
        repository.save(snapshot(record=rewritten))
    assert path.read_bytes() == before

    shortened = copy.deepcopy(original)
    shortened["messages"] = []
    with pytest.raises(ConversationIdentityConflict):
        repository.save(snapshot(record=shortened))
    assert path.read_bytes() == before


def test_adapter_accepts_append_only_canonical_history(repository):
    initial = canonical_record()
    repository.save(snapshot(record=initial))
    appended = copy.deepcopy(initial)
    appended["messages"].append({
        "message_id": "message-2",
        "conversation_id": appended["conversation_id"],
        "session_id": "session-1",
        "role": "user",
        "request_id": "request-message-2",
        "created_at": "2026-10-23T00:01:00Z",
        "content": "second message",
    })
    appended["requests"].append({
        "request_id": "request-message-2",
        "conversation_id": appended["conversation_id"],
        "session_id": "session-1",
        "message_id": "message-2",
        "state": "COMPLETED",
    })
    appended["rounds"].append({
        "round_id": f"{appended['conversation_id']}:request-message-2:round-1",
        "conversation_id": appended["conversation_id"],
        "session_id": "session-1",
        "message_id": "message-2",
        "request_id": "request-message-2",
        "round": 1,
        "status": "COMPLETED",
    })

    repository.save(snapshot(record=appended))
    restored = repository.load(OWNER_A, appended["conversation_id"])
    assert restored is not None
    assert len(restored.canonical_record["messages"]) == 2
    assert restored.canonical_record == appended


def test_storage_names_are_opaque_and_permissions_are_private(repository, tmp_path):
    candidate = snapshot()
    repository.save(candidate)
    path = repository._path_for(candidate.conversation_id)
    root = path.parent

    assert candidate.conversation_id not in path.name
    assert path.name.endswith(".json")
    assert (root.stat().st_mode & 0o777) == 0o700
    assert (path.stat().st_mode & 0o777) == 0o600
    assert ((root / ".repository.lock").stat().st_mode & 0o777) == 0o600


def test_record_checksum_corruption_fails_closed(repository):
    candidate = snapshot()
    repository.save(candidate)
    path = repository._path_for(candidate.conversation_id)
    envelope = json.loads(path.read_text(encoding="utf-8"))
    assert envelope["schema"] == FILE_REPOSITORY_SCHEMA
    envelope["canonical_record"]["messages"][0]["content"] = "tampered"
    path.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(ConversationRepositoryError, match="invalid or unreadable"):
        repository.load(OWNER_A, candidate.conversation_id)
    with pytest.raises(ConversationRepositoryError):
        repository.list_ids(OWNER_A)


def test_malformed_json_fails_closed(repository):
    candidate = snapshot()
    repository.save(candidate)
    path = repository._path_for(candidate.conversation_id)
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ConversationRepositoryError):
        repository.load(OWNER_A, candidate.conversation_id)


def test_invalid_list_limits_are_rejected(repository):
    for limit in (0, -1, True, "5"):
        with pytest.raises(ValueError, match="positive integer"):
            repository.list_ids(OWNER_A, limit=limit)


def test_write_does_not_leave_temporary_files_after_success(repository):
    candidate = snapshot()
    repository.save(candidate)
    assert list(repository._root.glob(".tmp-*")) == []


def test_unowned_or_missing_ids_have_same_delete_result(repository):
    candidate = snapshot()
    repository.save(candidate)

    assert repository.delete(OWNER_B, candidate.conversation_id) is False
    assert repository.delete(OWNER_A, "missing-id") is False
    assert repository.delete(OWNER_A, candidate.conversation_id) is True
