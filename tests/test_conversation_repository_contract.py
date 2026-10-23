"""Contract tests for the canonical conversation repository boundary.

The in-memory repository below is deliberately a test double, not a production
storage adapter. A future database adapter must satisfy this same contract.
"""
from __future__ import annotations

import copy
import pytest

from conversation_repository import (
    CANONICAL_STORE_CONTRACT,
    AccountIdentity,
    ConversationIdentityConflict,
    ConversationOwnershipError,
    ConversationRepository,
    OwnedConversationSnapshot,
)


OWNER_A = AccountIdentity("https://identity.example.test", "subject-A")
OWNER_B = AccountIdentity("https://identity.example.test", "subject-B")


def canonical_record(conversation_id="conv-1", message_id="msg-1"):
    request_id = f"req-{message_id}"
    round_id = f"{conversation_id}:{request_id}:r1"
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


class InMemoryRepositoryDouble:
    """Small test-only reference for repository contract expectations."""

    def __init__(self):
        self._rows = {}

    @staticmethod
    def _immutable_rows(record, collection, id_field, immutable_fields):
        return {
            str(row[id_field]): tuple(row.get(field) for field in immutable_fields)
            for row in record[collection]
            if row.get(id_field)
        }

    def save(self, snapshot):
        assert isinstance(snapshot, OwnedConversationSnapshot)
        cid = snapshot.conversation_id
        record = snapshot.canonical_record
        existing = self._rows.get(cid)
        if existing is not None:
            if existing.owner != snapshot.owner:
                raise ConversationOwnershipError("conversation owner mismatch")
            old_record = existing.canonical_record
            contracts = (
                ("messages", "message_id", ("conversation_id", "session_id", "role", "request_id", "created_at")),
                ("requests", "request_id", ("conversation_id", "session_id", "message_id")),
                ("rounds", "round_id", ("conversation_id", "session_id", "message_id", "request_id", "round")),
            )
            for collection, id_field, fields in contracts:
                old_rows = self._immutable_rows(old_record, collection, id_field, fields)
                new_rows = self._immutable_rows(record, collection, id_field, fields)
                if not set(old_rows).issubset(new_rows):
                    raise ConversationIdentityConflict("canonical history cannot be silently removed")
                if any(new_rows[key] != value for key, value in old_rows.items()):
                    raise ConversationIdentityConflict("canonical identity binding cannot be rewritten")
        self._rows[cid] = OwnedConversationSnapshot(snapshot.owner, record)

    def load(self, owner, conversation_id):
        row = self._rows.get(str(conversation_id or "").strip())
        if row is None or row.owner != owner:
            return None
        return OwnedConversationSnapshot(row.owner, row.canonical_record)

    def list_ids(self, owner, *, limit=50):
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("limit must be a positive integer")
        owned = [cid for cid, row in self._rows.items() if row.owner == owner]
        return sorted(owned)[:limit]

    def delete(self, owner, conversation_id):
        cid = str(conversation_id or "").strip()
        row = self._rows.get(cid)
        if row is None or row.owner != owner:
            return False
        del self._rows[cid]
        return True


def test_account_identity_trims_but_does_not_change_subject_case():
    identity = AccountIdentity(" https://id.example.test ", " Subject-AbC ")
    assert identity.issuer == "https://id.example.test"
    assert identity.subject == "Subject-AbC"
    assert identity.key == ("https://id.example.test", "Subject-AbC")


@pytest.mark.parametrize(
    "issuer,subject",
    [
        ("", "subject"),
        ("issuer", ""),
        ("issuer", "   "),
        ("issuer\ninvalid", "subject"),
        ("issuer", "subject\x7f"),
    ],
)
def test_account_identity_rejects_empty_or_control_values(issuer, subject):
    with pytest.raises(ValueError):
        AccountIdentity(issuer, subject)


def test_owned_snapshot_requires_canonical_contract_and_identity():
    record = canonical_record()
    snapshot = OwnedConversationSnapshot(OWNER_A, record)
    assert snapshot.conversation_id == "conv-1"
    assert snapshot.canonical_record == record

    no_contract = copy.deepcopy(record)
    no_contract.pop("canonical_store_contract")
    with pytest.raises(ValueError, match="canonical conversation store"):
        OwnedConversationSnapshot(OWNER_A, no_contract)

    no_id = copy.deepcopy(record)
    no_id["conversation_id"] = ""
    with pytest.raises(ValueError, match="conversation_id"):
        OwnedConversationSnapshot(OWNER_A, no_id)


def test_owned_snapshot_defensively_copies_input_and_output():
    record = canonical_record()
    snapshot = OwnedConversationSnapshot(OWNER_A, record)
    record["messages"][0]["role"] = "changed-after-construction"
    returned = snapshot.canonical_record
    returned["messages"][0]["role"] = "changed-after-read"
    assert snapshot.canonical_record["messages"][0]["role"] == "user"


def test_owned_snapshot_rejects_duplicate_canonical_ids_and_non_json_data():
    duplicate = canonical_record()
    duplicate["messages"].append(copy.deepcopy(duplicate["messages"][0]))
    with pytest.raises(ValueError, match="duplicate canonical message_id"):
        OwnedConversationSnapshot(OWNER_A, duplicate)

    not_json = canonical_record()
    not_json["unexpected_object"] = object()
    with pytest.raises(ValueError, match="JSON-compatible"):
        OwnedConversationSnapshot(OWNER_A, not_json)


def test_reference_repository_meets_protocol_shape_and_isolates_owners():
    repo = InMemoryRepositoryDouble()
    assert isinstance(repo, ConversationRepository)
    snapshot = OwnedConversationSnapshot(OWNER_A, canonical_record())
    repo.save(snapshot)
    repo.save(snapshot)  # unchanged writes are idempotent

    assert repo.list_ids(OWNER_A) == ["conv-1"]
    assert repo.list_ids(OWNER_B) == []
    assert repo.load(OWNER_A, "conv-1").canonical_record == canonical_record()
    assert repo.load(OWNER_B, "conv-1") is None
    assert repo.delete(OWNER_B, "conv-1") is False
    assert repo.delete(OWNER_A, "conv-1") is True
    assert repo.load(OWNER_A, "conv-1") is None


def test_reference_repository_refuses_owner_takeover():
    repo = InMemoryRepositoryDouble()
    repo.save(OwnedConversationSnapshot(OWNER_A, canonical_record()))
    with pytest.raises(ConversationOwnershipError):
        repo.save(OwnedConversationSnapshot(OWNER_B, canonical_record()))


def test_reference_repository_refuses_canonical_identity_rewrite_or_history_loss():
    repo = InMemoryRepositoryDouble()
    repo.save(OwnedConversationSnapshot(OWNER_A, canonical_record()))

    changed = canonical_record()
    changed["messages"][0]["request_id"] = "another-request"
    with pytest.raises(ConversationIdentityConflict):
        repo.save(OwnedConversationSnapshot(OWNER_A, changed))

    shortened = canonical_record()
    shortened["messages"] = []
    with pytest.raises(ConversationIdentityConflict):
        repo.save(OwnedConversationSnapshot(OWNER_A, shortened))


def test_reference_repository_rejects_invalid_list_limit():
    repo = InMemoryRepositoryDouble()
    with pytest.raises(ValueError, match="positive integer"):
        repo.list_ids(OWNER_A, limit=0)
    with pytest.raises(ValueError, match="positive integer"):
        repo.list_ids(OWNER_A, limit=True)
