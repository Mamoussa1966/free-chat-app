"""Unit/security tests for the Supabase conversation adapter.

The HTTP test double models JWT-bound RLS behavior so CI needs no live project,
credentials, or network access. Real PostgreSQL policy checks live in
supabase/tests/council_conversations_rls.test.sql and require a local Supabase
test database before the adapter is enabled in the deployed app.
"""
from __future__ import annotations

import copy
import hashlib
import json
import uuid

import pytest

from conversation_repository import (
    CANONICAL_STORE_CONTRACT,
    AccountIdentity,
    ConversationIdentityConflict,
    ConversationOwnershipError,
    ConversationRepository,
    ConversationRepositoryError,
    OwnedConversationSnapshot,
)
from supabase_conversation_repository import (
    SUPABASE_CONVERSATION_SCHEMA,
    SupabaseConversationRepository,
)


PROJECT_URL = "https://council-test.supabase.co"
ISSUER = PROJECT_URL + "/auth/v1"
PUBLISHABLE_KEY = "sb_publishable_test_key"
OWNER_A = AccountIdentity(ISSUER, "00000000-0000-0000-0000-00000000000a")
OWNER_B = AccountIdentity(ISSUER, "00000000-0000-0000-0000-00000000000b")
TOKEN_OWNERS = {
    "test-user-jwt-A": OWNER_A.subject,
    "test-user-jwt-B": OWNER_B.subject,
}


def canonical_record(conversation_id="conversation-1", message_id="message-1", body="hello"):
    request_id = "request-" + message_id
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
            "content": body,
        }],
        "requests": [{
            "request_id": request_id,
            "conversation_id": conversation_id,
            "session_id": "session-1",
            "message_id": message_id,
            "created_at": "2026-10-23T00:00:01Z",
            "state": "COMPLETED",
        }],
        "rounds": [{
            "round_id": round_id,
            "conversation_id": conversation_id,
            "session_id": "session-1",
            "message_id": message_id,
            "request_id": request_id,
            "round": 1,
            "round_number": 1,
            "canonical_round_base": 1,
            "canonical_round_record_id": round_id,
            "canonical_identity_key": round_id,
            "created_at": "2026-10-23T00:00:02Z",
            "status": "COMPLETED",
        }],
    }


class FakeResponse:
    def __init__(self, status_code, data=None):
        self.status_code = status_code
        self._data = copy.deepcopy(data)
        self.text = "" if data is None else json.dumps(data)

    def json(self):
        return copy.deepcopy(self._data)


class RlsFakeSession:
    """In-memory PostgREST stand-in: visible rows are always scoped by JWT subject."""

    def __init__(self):
        self.rows = {}
        self.calls = []

    @staticmethod
    def _assert_append_only(previous, candidate):
        for collection, id_field, fields in (
            ("messages", "message_id", ("conversation_id", "session_id", "role", "request_id", "created_at")),
            ("requests", "request_id", ("conversation_id", "session_id", "message_id", "created_at")),
            ("rounds", "round_id", (
                "conversation_id", "session_id", "message_id", "request_id", "round",
                "round_number", "canonical_round_base", "canonical_round_record_id",
                "canonical_identity_key", "created_at",
            )),
        ):
            old_by_id = {row[id_field]: row for row in previous[collection]}
            new_by_id = {row[id_field]: row for row in candidate[collection]}
            if not set(old_by_id).issubset(new_by_id):
                raise ConversationIdentityConflict("canonical history cannot be removed")
            for identity, old in old_by_id.items():
                for field in fields:
                    if old.get(field) not in (None, "") and new_by_id[identity].get(field) != old[field]:
                        raise ConversationIdentityConflict("canonical identity binding cannot be rewritten")

    def request(self, method, url, *, params=None, json=None, headers=None, timeout=None):
        params = dict(params or {})
        headers = dict(headers or {})
        self.calls.append({
            "method": method, "url": url, "params": params,
            "json": copy.deepcopy(json), "headers": headers, "timeout": timeout,
        })
        if headers.get("apikey") != PUBLISHABLE_KEY:
            return FakeResponse(401, {"message": "invalid publishable key"})
        if not url.endswith("/rest/v1/council_conversations"):
            return FakeResponse(404, {"message": "not found"})
        bearer = headers.get("Authorization", "")
        token = bearer.removeprefix("Bearer ")
        owner_id = TOKEN_OWNERS.get(token)
        if not owner_id:
            return FakeResponse(401, {"message": "invalid JWT"})
        if method == "GET":
            rows = []
            requested_id = params.get("conversation_id")
            requested_owner = params.get("owner_id")
            for row in self.rows.values():
                # This is the essential server-side RLS simulation, not just a query filter.
                if row["owner_id"] != owner_id:
                    continue
                if requested_owner and requested_owner != f"eq.{owner_id}":
                    continue
                if requested_id and requested_id != f"eq.{row['conversation_id']}":
                    continue
                select = params.get("select", "conversation_id,owner_id,schema,canonical_record,checksum")
                selected = {key: copy.deepcopy(row[key]) for key in select.split(",") if key in row}
                rows.append(selected)
            return FakeResponse(200, rows)
        if method == "POST":
            candidate = copy.deepcopy(json or {})
            if candidate.get("owner_id") != owner_id:
                return FakeResponse(403, {"message": "row-level security violation"})
            cid = candidate.get("conversation_id")
            existing = self.rows.get(cid)
            if existing is not None and existing["owner_id"] != owner_id:
                # Model an RLS-hidden conflict without revealing the existing owner.
                return FakeResponse(201, [])
            if existing is not None:
                try:
                    self._assert_append_only(existing["canonical_record"], candidate["canonical_record"])
                except ConversationIdentityConflict:
                    return FakeResponse(409, {"message": "immutable identity conflict"})
            candidate.setdefault("created_at", "2026-10-23T00:00:00Z")
            candidate["updated_at"] = "2026-10-23T00:00:01Z"
            self.rows[cid] = candidate
            return FakeResponse(201, [candidate])
        if method == "DELETE":
            cid_filter = params.get("conversation_id", "")
            cid = cid_filter.removeprefix("eq.")
            row = self.rows.get(cid)
            if row is None or row["owner_id"] != owner_id:
                return FakeResponse(200, [])
            del self.rows[cid]
            return FakeResponse(200, [{"conversation_id": cid, "owner_id": owner_id}])
        return FakeResponse(405, {"message": "method not allowed"})


@pytest.fixture
def fake_session():
    return RlsFakeSession()


def make_repository(owner, token, session):
    return SupabaseConversationRepository(
        supabase_url=PROJECT_URL,
        publishable_key=PUBLISHABLE_KEY,
        access_token=token,
        authenticated_identity=owner,
        session=session,
    )


def test_adapter_satisfies_protocol_and_uses_user_jwt_plus_publishable_key(fake_session):
    repo = make_repository(OWNER_A, "test-user-jwt-A", fake_session)
    assert isinstance(repo, ConversationRepository)
    repo.save(OwnedConversationSnapshot(OWNER_A, canonical_record()))
    call = next(call for call in fake_session.calls if call["method"] == "POST")
    assert call["headers"]["apikey"] == PUBLISHABLE_KEY
    assert call["headers"]["Authorization"] == "Bearer test-user-jwt-A"
    assert "service_role" not in repr(call["headers"])
    assert "sb_secret_" not in repr(call["headers"])


def test_two_users_are_isolated_for_load_list_save_and_delete(fake_session):
    repo_a = make_repository(OWNER_A, "test-user-jwt-A", fake_session)
    repo_b = make_repository(OWNER_B, "test-user-jwt-B", fake_session)
    snapshot_a = OwnedConversationSnapshot(OWNER_A, canonical_record())
    repo_a.save(snapshot_a)

    assert repo_a.load(OWNER_A, snapshot_a.conversation_id).canonical_record == snapshot_a.canonical_record
    assert repo_a.list_ids(OWNER_A) == [snapshot_a.conversation_id]
    assert repo_b.load(OWNER_B, snapshot_a.conversation_id) is None
    assert repo_b.list_ids(OWNER_B) == []
    assert repo_b.delete(OWNER_B, snapshot_a.conversation_id) is False

    # A conflicting ID must not let account B overwrite account A, and the error
    # deliberately does not disclose that the identifier exists for another user.
    with pytest.raises(ConversationRepositoryError, match="did not confirm"):
        repo_b.save(OwnedConversationSnapshot(OWNER_B, canonical_record()))
    assert repo_a.load(OWNER_A, snapshot_a.conversation_id).canonical_record == snapshot_a.canonical_record
    assert repo_a.delete(OWNER_A, snapshot_a.conversation_id) is True
    assert repo_a.load(OWNER_A, snapshot_a.conversation_id) is None


def test_repository_refuses_an_identity_other_than_its_bound_session(fake_session):
    repo_a = make_repository(OWNER_A, "test-user-jwt-A", fake_session)
    with pytest.raises(ConversationOwnershipError):
        repo_a.load(OWNER_B, "conversation-1")
    with pytest.raises(ConversationOwnershipError):
        repo_a.list_ids(OWNER_B)
    with pytest.raises(ConversationOwnershipError):
        repo_a.delete(OWNER_B, "conversation-1")
    with pytest.raises(ConversationOwnershipError):
        repo_a.save(OwnedConversationSnapshot(OWNER_B, canonical_record()))


def test_adapter_requires_https_project_and_matching_issuer():
    with pytest.raises(ValueError, match="HTTPS"):
        SupabaseConversationRepository(
            supabase_url="http://council-test.supabase.co",
            publishable_key=PUBLISHABLE_KEY,
            access_token="test-user-jwt-A",
            authenticated_identity=OWNER_A,
        )
    wrong_issuer = AccountIdentity("https://other.supabase.co/auth/v1", OWNER_A.subject)
    with pytest.raises(ValueError, match="issuer"):
        SupabaseConversationRepository(
            supabase_url=PROJECT_URL,
            publishable_key=PUBLISHABLE_KEY,
            access_token="test-user-jwt-A",
            authenticated_identity=wrong_issuer,
        )
    non_uuid = AccountIdentity(ISSUER, "subject-A")
    with pytest.raises(ValueError, match="UUID"):
        SupabaseConversationRepository(
            supabase_url=PROJECT_URL,
            publishable_key=PUBLISHABLE_KEY,
            access_token="test-user-jwt-A",
            authenticated_identity=non_uuid,
        )


def test_save_is_idempotent_and_append_only_for_established_identity(fake_session):
    repo = make_repository(OWNER_A, "test-user-jwt-A", fake_session)
    record = canonical_record()
    snapshot = OwnedConversationSnapshot(OWNER_A, record)
    repo.save(snapshot)
    post_count = sum(call["method"] == "POST" for call in fake_session.calls)
    repo.save(snapshot)
    assert sum(call["method"] == "POST" for call in fake_session.calls) == post_count

    changed = copy.deepcopy(record)
    changed["messages"][0]["request_id"] = "tampered-request"
    with pytest.raises(ValueError):
        OwnedConversationSnapshot(OWNER_A, changed)

    # A valid candidate that changes an already established immutable field is rejected.
    changed = copy.deepcopy(record)
    changed["messages"][0]["role"] = "assistant"
    with pytest.raises(ConversationIdentityConflict):
        repo.save(OwnedConversationSnapshot(OWNER_A, changed))
    assert repo.load(OWNER_A, snapshot.conversation_id).canonical_record == record


def test_checksum_corruption_fails_closed(fake_session):
    repo = make_repository(OWNER_A, "test-user-jwt-A", fake_session)
    snapshot = OwnedConversationSnapshot(OWNER_A, canonical_record())
    repo.save(snapshot)
    fake_session.rows[snapshot.conversation_id]["canonical_record"]["messages"][0]["content"] = "tampered"
    with pytest.raises(ConversationRepositoryError, match="checksum"):
        repo.load(OWNER_A, snapshot.conversation_id)


def test_unknown_or_expired_access_token_fails_closed(fake_session):
    repo = make_repository(OWNER_A, "expired-or-invalid-token", fake_session)
    with pytest.raises(ConversationRepositoryError, match="session may have expired"):
        repo.load(OWNER_A, "conversation-1")


def test_list_limit_is_bounded_and_rejects_bool(fake_session):
    repo = make_repository(OWNER_A, "test-user-jwt-A", fake_session)
    for limit in (0, -1, True, "10", 501):
        with pytest.raises(ValueError, match="between 1 and 500"):
            repo.list_ids(OWNER_A, limit=limit)


def test_migration_defines_rls_grants_and_no_service_role_shortcut():
    from pathlib import Path

    migration = Path("supabase/migrations/20261023000000_council_conversations.sql").read_text(encoding="utf-8").lower()
    assert "enable row level security" in migration
    assert "force row level security" in migration
    for name in (
        "council_conversations_select_own",
        "council_conversations_insert_own",
        "council_conversations_update_own",
        "council_conversations_delete_own",
    ):
        assert name in migration
    assert "owner_id = (select auth.uid())" in migration
    assert "security definer" not in migration
    assert "grant select, insert, update, delete on table public.council_conversations to authenticated" in migration
    assert "from public, anon, authenticated, service_role" in migration
    assert "grant select, insert, update, delete on table public.council_conversations to service_role" not in migration


def test_rows_use_a_canonical_record_checksum_not_a_client_supplied_owner_id(fake_session):
    record = canonical_record()
    repo = make_repository(OWNER_A, "test-user-jwt-A", fake_session)
    snapshot = OwnedConversationSnapshot(OWNER_A, record)
    repo.save(snapshot)
    stored = fake_session.rows[snapshot.conversation_id]
    encoded = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    expected_checksum = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    assert stored["checksum"] == expected_checksum
    assert len(stored["checksum"]) == 64
    assert stored["owner_id"] == OWNER_A.subject
    assert str(uuid.UUID(OWNER_A.subject)) == OWNER_A.subject
    assert SUPABASE_CONVERSATION_SCHEMA == "ai-council-supabase-conversation/v1"
