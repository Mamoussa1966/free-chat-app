"""Contract tests for the Supabase PostgREST adapter using a deterministic fake.

No network, Supabase project, real auth token, database credential, or provider key
is required. The fake enforces the same principal scoping expected from RLS; the
SQL migration has separate assertions to make the database policies reviewable.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import uuid

import pytest

from conversation_repository import (
    CANONICAL_STORE_CONTRACT,
    AccountIdentity,
    ConversationAuthenticationError,
    ConversationIdentityConflict,
    ConversationOwnershipError,
    ConversationRepository,
    ConversationRepositoryError,
    OwnedConversationSnapshot,
)
from supabase_conversation_repository import SupabaseConversationRepository, _eq_filter

BASE_URL = "https://council-test.supabase.co"
ISSUER = BASE_URL + "/auth/v1"
ANON_KEY = "test-public-anon-key"
USER_A_ID = "11111111-1111-4111-8111-111111111111"
USER_B_ID = "22222222-2222-4222-8222-222222222222"
OWNER_A = AccountIdentity(ISSUER, USER_A_ID)
OWNER_B = AccountIdentity(ISSUER, USER_B_ID)


def canonical_record(conversation_id="conversation-1", message_id="message-1"):
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
            "content": "private conversation text",
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
            "ordinal": 1,
            "canonical_round_base": 1,
            "canonical_round_record_id": round_id,
            "canonical_identity_key": round_id,
            "created_at": "2026-10-23T00:00:02Z",
            "status": "COMPLETED",
        }],
    }


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = copy.deepcopy(body)
        self.text = json.dumps(body, ensure_ascii=False)

    def json(self):
        return copy.deepcopy(self._body)


class FakeSupabase:
    """Shared server state; each session presents one signed-in user token."""

    def __init__(self):
        self.users = {"token-user-a": USER_A_ID, "token-user-b": USER_B_ID}
        self.rows = {}
        self.calls = []

    @staticmethod
    def _filter_value(value):
        if not isinstance(value, str) or not value.startswith("eq."):
            return None
        rest = value[3:]
        if len(rest) >= 2 and rest[0] == '"' and rest[-1] == '"':
            rest = rest[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        return rest

    def request(self, method, url, *, headers, params=None, json=None, timeout=None):
        params = dict(params or {})
        self.calls.append({
            "method": method,
            "url": url,
            "headers": dict(headers),
            "params": copy.deepcopy(params),
            "json": copy.deepcopy(json),
        })
        token = str(headers.get("Authorization") or "").removeprefix("Bearer ")
        current_user = self.users.get(token)

        if url.endswith("/auth/v1/user"):
            if current_user is None:
                return FakeResponse(401, {"message": "invalid token"})
            return FakeResponse(200, {"id": current_user, "email": "not-used@example.test"})

        if "/rest/v1/ai_council_conversations" not in url:
            return FakeResponse(404, {"message": "unknown endpoint"})
        if current_user is None:
            return FakeResponse(401, {"message": "invalid token"})

        if method == "GET":
            cid = self._filter_value(params.get("conversation_id")) if params.get("conversation_id") else None
            requested_owner = self._filter_value(params.get("owner_id")) if params.get("owner_id") else None
            rows = [
                copy.deepcopy(row)
                for row in self.rows.values()
                if row["owner_id"] == current_user
                and (cid is None or row["conversation_id"] == cid)
                and (requested_owner is None or row["owner_id"] == requested_owner)
            ]
            rows.sort(key=lambda row: row.get("updated_at", ""), reverse=True)
            rows = rows[:int(params.get("limit", "50"))]
            selected = params.get("select")
            if selected and selected != "*":
                fields = [part.strip() for part in selected.split(",")]
                rows = [{key: row[key] for key in fields if key in row} for row in rows]
            return FakeResponse(200, rows)

        if method == "POST":
            payload = copy.deepcopy(json or {})
            cid = payload.get("conversation_id")
            if payload.get("owner_id") != current_user:
                return FakeResponse(403, {"message": "row-level security violation"})
            if cid in self.rows:
                return FakeResponse(409, {"message": "unique constraint"})
            row = {
                **payload,
                "created_at": "2026-10-23T00:00:00Z",
                "updated_at": payload.get("updated_at", "2026-10-23T00:00:00Z"),
            }
            self.rows[cid] = row
            return FakeResponse(201, [copy.deepcopy(row)])

        if method == "PATCH":
            cid = self._filter_value(params.get("conversation_id"))
            requested_owner = self._filter_value(params.get("owner_id"))
            row = self.rows.get(cid)
            if row is None or row["owner_id"] != current_user or requested_owner != current_user:
                return FakeResponse(200, [])
            row.update(copy.deepcopy(json or {}))
            return FakeResponse(200, [copy.deepcopy(row)])

        if method == "DELETE":
            cid = self._filter_value(params.get("conversation_id"))
            requested_owner = self._filter_value(params.get("owner_id"))
            row = self.rows.get(cid)
            if row is None or row["owner_id"] != current_user or requested_owner != current_user:
                return FakeResponse(200, [])
            del self.rows[cid]
            return FakeResponse(200, [{"conversation_id": cid}])

        return FakeResponse(405, {"message": "method not allowed"})


@pytest.fixture
def backend():
    return FakeSupabase()


def make_repository(backend, token="token-user-a"):
    return SupabaseConversationRepository(
        BASE_URL,
        ANON_KEY,
        token,
        session=backend,
    )


def make_snapshot(owner=OWNER_A, record=None):
    return OwnedConversationSnapshot(owner, record if record is not None else canonical_record())


def test_supabase_adapter_implements_repository_protocol_and_roundtrips(backend):
    repo = make_repository(backend)
    snapshot = make_snapshot()
    assert isinstance(repo, ConversationRepository)

    repo.save(snapshot)
    restored = make_repository(backend).load(OWNER_A, snapshot.conversation_id)

    assert restored is not None
    assert restored.owner == OWNER_A
    assert restored.canonical_record == snapshot.canonical_record
    assert make_repository(backend).list_ids(OWNER_A) == ["conversation-1"]


def test_two_users_are_isolated_for_load_list_save_and_delete(backend):
    repo_a = make_repository(backend, "token-user-a")
    repo_b = make_repository(backend, "token-user-b")
    snapshot = make_snapshot()
    repo_a.save(snapshot)

    assert repo_a.load(OWNER_A, snapshot.conversation_id) is not None
    assert repo_b.load(OWNER_B, snapshot.conversation_id) is None
    assert repo_a.list_ids(OWNER_A) == [snapshot.conversation_id]
    assert repo_b.list_ids(OWNER_B) == []
    assert repo_b.delete(OWNER_B, snapshot.conversation_id) is False
    with pytest.raises(ConversationOwnershipError):
        repo_b.save(make_snapshot(OWNER_B, snapshot.canonical_record))
    assert repo_a.load(OWNER_A, snapshot.conversation_id).canonical_record == snapshot.canonical_record


def test_access_token_identity_must_match_supplied_owner_before_data_operations(backend):
    repo_a = make_repository(backend, "token-user-a")
    with pytest.raises(ConversationOwnershipError, match="does not match"):
        repo_a.load(OWNER_B, "conversation-1")
    assert not any("/rest/v1/" in call["url"] for call in backend.calls)


def test_invalid_or_expired_access_token_fails_closed(backend):
    repo = make_repository(backend, "not-a-real-token")
    with pytest.raises(ConversationAuthenticationError):
        repo.load(OWNER_A, "conversation-1")
    assert backend.rows == {}


def test_owner_update_is_append_only_and_preserves_existing_bindings(backend):
    repo = make_repository(backend)
    original = canonical_record()
    repo.save(make_snapshot(record=original))

    appended = copy.deepcopy(original)
    appended["messages"].append({
        "message_id": "message-2",
        "conversation_id": "conversation-1",
        "session_id": "session-1",
        "role": "user",
        "request_id": "request-message-2",
        "created_at": "2026-10-23T00:01:00Z",
        "content": "second message",
    })
    appended["requests"].append({
        "request_id": "request-message-2",
        "conversation_id": "conversation-1",
        "session_id": "session-1",
        "message_id": "message-2",
        "created_at": "2026-10-23T00:01:01Z",
        "state": "COMPLETED",
    })
    appended_round_id = "conversation-1:request-message-2:r1"
    appended["rounds"].append({
        "round_id": appended_round_id,
        "conversation_id": "conversation-1",
        "session_id": "session-1",
        "message_id": "message-2",
        "request_id": "request-message-2",
        "round": 2,
        "round_number": 2,
        "ordinal": 2,
        "canonical_round_base": 2,
        "canonical_round_record_id": appended_round_id,
        "canonical_identity_key": appended_round_id,
        "created_at": "2026-10-23T00:01:02Z",
        "status": "COMPLETED",
    })

    repo.save(make_snapshot(record=appended))
    assert repo.load(OWNER_A, "conversation-1").canonical_record == appended


def test_rewriting_immutable_history_and_erasing_history_are_rejected(backend):
    repo = make_repository(backend)
    original = canonical_record()
    repo.save(make_snapshot(record=original))

    rewritten = copy.deepcopy(original)
    rewritten["messages"][0]["role"] = "assistant"
    with pytest.raises(ConversationIdentityConflict):
        repo.save(make_snapshot(record=rewritten))

    erased = copy.deepcopy(original)
    erased["messages"] = []
    erased["requests"] = []
    erased["rounds"] = []
    with pytest.raises(ConversationIdentityConflict):
        repo.save(make_snapshot(record=erased))

    assert repo.load(OWNER_A, "conversation-1").canonical_record == original


def test_unchanged_save_is_idempotent(backend):
    repo = make_repository(backend)
    snapshot = make_snapshot()
    repo.save(snapshot)
    before = copy.deepcopy(backend.rows["conversation-1"])
    repo.save(snapshot)
    assert backend.rows["conversation-1"] == before


def test_checksum_detects_a_tampered_stored_snapshot(backend):
    repo = make_repository(backend)
    repo.save(make_snapshot())
    damaged = canonical_record()
    damaged["messages"][0]["content"] = "tampered"
    backend.rows["conversation-1"]["canonical_record_json"] = json.dumps(
        damaged, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    with pytest.raises(ConversationRepositoryError, match="integrity validation"):
        repo.load(OWNER_A, "conversation-1")


def test_access_headers_use_user_jwt_and_never_a_service_role_key(backend):
    repo = make_repository(backend)
    repo.save(make_snapshot())
    calls = [call for call in backend.calls if "/rest/v1/" in call["url"]]
    assert calls
    for call in calls:
        assert call["headers"]["apikey"] == ANON_KEY
        assert call["headers"]["Authorization"] == "Bearer token-user-a"
        assert "service_role" not in call["headers"]["apikey"]
        assert call["headers"]["Authorization"] != "Bearer service_role"


@pytest.mark.parametrize("limit", [0, -1, True, "4", 501])
def test_invalid_list_limits_are_rejected(backend, limit):
    with pytest.raises(ValueError, match="between 1 and 500"):
        make_repository(backend).list_ids(OWNER_A, limit=limit)


def test_postgrest_filter_quotes_opaque_conversation_ids():
    assert _eq_filter("conversation-1") == "eq.conversation-1"
    assert _eq_filter('conversation,owner_id=eq."other"') == 'eq."conversation,owner_id=eq.\\"other\\""'


def test_database_migration_enables_separate_rls_policies_for_every_operation():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "supabase"
        / "migrations"
        / "20261023210000_create_ai_council_conversations.sql"
    )
    sql = migration_path.read_text(encoding="utf-8").lower()
    assert "enable row level security" in sql
    assert "force row level security" in sql
    assert "revoke all on table public.ai_council_conversations from anon, authenticated" in sql
    assert "grant select, insert, update, delete on table public.ai_council_conversations to authenticated" in sql
    for operation in ("select", "insert", "update", "delete"):
        assert f"for {operation}" in sql
    assert sql.count("auth.uid()") >= 8
    assert "with check" in sql
    assert "snapshot_sha256" in sql
    assert "service_role" not in sql
