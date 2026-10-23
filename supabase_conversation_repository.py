"""Supabase Auth + PostgREST adapter for canonical conversation snapshots.

The adapter uses only a Supabase anon/publishable key plus the signed-in user's
access token. It deliberately does not accept or use service_role credentials.
Row ownership is enforced by Postgres Row Level Security (RLS) and is also
checked in each REST filter. This adapter is not wired into the Streamlit app;
callers must obtain the access token through a verified Supabase Auth flow.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
import uuid

import requests

from conversation_repository import (
    AccountIdentity,
    ConversationAuthenticationError,
    ConversationIdentityConflict,
    ConversationOwnershipError,
    ConversationRepository,
    ConversationRepositoryError,
    OwnedConversationSnapshot,
)

SUPABASE_TABLE = "ai_council_conversations"
SUPABASE_SCHEMA = "public"
SUPABASE_REPOSITORY_SCHEMA = "ai-council-supabase-conversation-repository/v1"
_ID_FIELDS = {
    "messages": (
        "message_id",
        ("conversation_id", "session_id", "role", "request_id", "created_at"),
    ),
    "requests": (
        "request_id",
        ("conversation_id", "session_id", "message_id", "created_at"),
    ),
    "rounds": (
        "round_id",
        (
            "conversation_id",
            "session_id",
            "message_id",
            "request_id",
            "round",
            "round_number",
            "round_no",
            "ordinal",
            "round_ordinal",
            "canonical_round_base",
            "canonical_round_record_id",
            "canonical_identity_key",
            "created_at",
        ),
    ),
}
_SAFE_FILTER_VALUE = re.compile(r"^[A-Za-z0-9_:\-]+$")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _snapshot_checksum(record: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(record).encode("utf-8")).hexdigest()


def _eq_filter(value: str) -> str:
    """Build a single PostgREST eq filter without changing opaque IDs."""
    if _SAFE_FILTER_VALUE.fullmatch(value):
        return f"eq.{value}"
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'eq."{escaped}"'


def _identity_rows(record: dict[str, Any], collection: str) -> dict[str, dict[str, Any]]:
    id_field, immutable_fields = _ID_FIELDS[collection]
    rows: dict[str, dict[str, Any]] = {}
    for row in record.get(collection, []):
        if not isinstance(row, dict):
            raise ConversationRepositoryError("canonical identity record is malformed")
        identity = str(row.get(id_field) or "").strip()
        if not identity:
            continue
        rows[identity] = {
            field: row.get(field)
            for field in immutable_fields
            if row.get(field) not in (None, "")
        }
    return rows


def _assert_history_preserved(previous: dict[str, Any], candidate: dict[str, Any]) -> None:
    """Require append-only identity history while allowing result/status enrichment."""
    for collection in _ID_FIELDS:
        old_rows = _identity_rows(previous, collection)
        new_rows = _identity_rows(candidate, collection)
        if not set(old_rows).issubset(new_rows):
            raise ConversationIdentityConflict(
                f"canonical {collection} history cannot be silently removed"
            )
        for identity, old_values in old_rows.items():
            new_values = new_rows[identity]
            if any(new_values.get(field) != value for field, value in old_values.items()):
                raise ConversationIdentityConflict(
                    f"canonical {collection} identity binding cannot be rewritten"
                )


class SupabaseConversationRepository:
    """Owner-scoped PostgreSQL repository using Supabase Auth and PostgREST.

    Required constructor values are project URL, public anon/publishable key,
    and the current signed-in user's access token. The token is verified via
    /auth/v1/user for every public operation; caller-supplied identity data is
    never treated as proof of authentication. The database RLS policies remain
    the security boundary; filtering by owner_id is an additional safeguard.

    The implementation uses the existing Requests dependency and does not
    require supabase-py, service_role access, a DB password, or production
    Secrets changes. It does not authenticate users or manage token refresh.
    """

    def __init__(
        self,
        supabase_url: str,
        anon_key: str,
        access_token: str,
        *,
        session: Any | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        parsed = urlparse(str(supabase_url or "").strip())
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or (parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"})
        ):
            raise ValueError("supabase_url must be an HTTPS project URL")
        if not isinstance(anon_key, str) or not anon_key.strip():
            raise ValueError("anon_key is required")
        if not isinstance(access_token, str) or not access_token.strip():
            raise ValueError("access_token is required")
        if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self._base_url = f"{parsed.scheme}://{parsed.netloc}"
        self._issuer = f"{self._base_url}/auth/v1"
        self._anon_key = anon_key.strip()
        self._access_token = access_token.strip()
        self._timeout_seconds = float(timeout_seconds)
        self._session = session if session is not None else requests.Session()

    @property
    def identity_issuer(self) -> str:
        """Stable issuer string used to bind AccountIdentity to this Supabase project."""
        return self._issuer

    def _headers(self, *, prefer: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self._anon_key,
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _send(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        prefer: str | None = None,
    ) -> Any:
        try:
            return self._session.request(
                method,
                f"{self._base_url}{path}",
                headers=self._headers(prefer=prefer),
                params=params,
                json=payload,
                timeout=self._timeout_seconds,
            )
        except requests.RequestException:
            # Never propagate request diagnostics that could include request
            # details; callers get a stable, secret-safe error instead.
            raise ConversationRepositoryError("Supabase request failed") from None

    @staticmethod
    def _json(response: Any, *, context: str) -> Any:
        status = int(getattr(response, "status_code", 0) or 0)
        if status in {401, 403} and context == "auth":
            raise ConversationAuthenticationError(
                "Supabase access token is invalid, expired, or not authorized"
            )
        if status < 200 or status >= 300:
            raise ConversationRepositoryError(
                f"Supabase {context} request was rejected (HTTP {status})"
            )
        try:
            return response.json()
        except (ValueError, AttributeError):
            raise ConversationRepositoryError(
                f"Supabase {context} response was not valid JSON"
            ) from None

    def _current_identity(self) -> AccountIdentity:
        response = self._send("GET", "/auth/v1/user")
        payload = self._json(response, context="auth")
        user_id = payload.get("id") if isinstance(payload, dict) else None
        try:
            canonical_user_id = str(uuid.UUID(str(user_id)))
        except (ValueError, TypeError, AttributeError):
            raise ConversationAuthenticationError(
                "Supabase did not return a valid authenticated user identity"
            ) from None
        return AccountIdentity(self._issuer, canonical_user_id)

    def _assert_owner(self, owner: AccountIdentity) -> str:
        if not isinstance(owner, AccountIdentity):
            raise ConversationAuthenticationError("a verified AccountIdentity is required")
        actual = self._current_identity()
        if actual != owner:
            raise ConversationOwnershipError(
                "requested owner does not match the authenticated Supabase user"
            )
        return actual.subject

    @staticmethod
    def _validate_conversation_id(conversation_id: str) -> str:
        if not isinstance(conversation_id, str):
            raise ValueError("conversation_id must be a string")
        value = conversation_id.strip()
        if (
            not value
            or value != conversation_id
            or len(value) > 1024
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
        ):
            raise ValueError("conversation_id is invalid")
        return value

    def _row_params(self, conversation_id: str, owner_id: str) -> dict[str, str]:
        return {
            "select": "conversation_id,owner_id,canonical_record_json,snapshot_sha256,created_at,updated_at",
            "conversation_id": _eq_filter(conversation_id),
            "owner_id": _eq_filter(owner_id),
            "limit": "1",
        }

    def _read_owned_row(self, owner: AccountIdentity, owner_id: str, conversation_id: str) -> dict[str, Any] | None:
        response = self._send(
            "GET",
            f"/rest/v1/{SUPABASE_TABLE}",
            params=self._row_params(conversation_id, owner_id),
        )
        rows = self._json(response, context="read")
        if not isinstance(rows, list):
            raise ConversationRepositoryError("Supabase returned an invalid conversation row set")
        if not rows:
            return None
        row = rows[0]
        if not isinstance(row, dict):
            raise ConversationRepositoryError("Supabase returned an invalid conversation row")
        if str(row.get("owner_id") or "") != owner_id:
            # RLS should make this impossible. Fail closed if the response ever
            # violates the expected boundary, without returning any row details.
            raise ConversationRepositoryError("Supabase owner isolation check failed")
        if str(row.get("conversation_id") or "") != conversation_id:
            raise ConversationRepositoryError("Supabase conversation identity check failed")
        return row

    def _decode_row(
        self, owner: AccountIdentity, owner_id: str, row: dict[str, Any]
    ) -> OwnedConversationSnapshot:
        record_json = row.get("canonical_record_json")
        if not isinstance(record_json, str):
            raise ConversationRepositoryError("stored conversation snapshot is invalid")
        stored_checksum = row.get("snapshot_sha256")
        expected_checksum = hashlib.sha256(record_json.encode("utf-8")).hexdigest()
        if not isinstance(stored_checksum, str) or not hmac.compare_digest(
            expected_checksum, stored_checksum
        ):
            raise ConversationRepositoryError("stored conversation snapshot failed integrity validation")
        try:
            record = json.loads(record_json)
            if not isinstance(record, dict) or _canonical_json(record) != record_json:
                raise ValueError("snapshot encoding is not canonical")
            snapshot = OwnedConversationSnapshot(owner, record)
        except (TypeError, ValueError):
            raise ConversationRepositoryError("stored canonical conversation failed validation") from None
        if snapshot.conversation_id != str(row.get("conversation_id") or ""):
            raise ConversationRepositoryError("stored conversation identity does not match its key")
        if str(row.get("owner_id") or "") != owner_id:
            raise ConversationRepositoryError("stored conversation owner validation failed")
        return snapshot

    def load(self, owner: AccountIdentity, conversation_id: str) -> OwnedConversationSnapshot | None:
        owner_id = self._assert_owner(owner)
        conversation_id = self._validate_conversation_id(conversation_id)
        row = self._read_owned_row(owner, owner_id, conversation_id)
        if row is None:
            return None
        return self._decode_row(owner, owner_id, row)

    def list_ids(self, owner: AccountIdentity, *, limit: int = 50) -> list[str]:
        owner_id = self._assert_owner(owner)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 500:
            raise ValueError("limit must be an integer between 1 and 500")
        response = self._send(
            "GET",
            f"/rest/v1/{SUPABASE_TABLE}",
            params={
                "select": "conversation_id,owner_id",
                "owner_id": _eq_filter(owner_id),
                "order": "updated_at.desc",
                "limit": str(limit),
            },
        )
        rows = self._json(response, context="list")
        if not isinstance(rows, list):
            raise ConversationRepositoryError("Supabase returned an invalid conversation list")
        result: list[str] = []
        for row in rows:
            if not isinstance(row, dict) or str(row.get("owner_id") or "") != owner_id:
                raise ConversationRepositoryError("Supabase owner isolation check failed")
            cid = row.get("conversation_id")
            if not isinstance(cid, str) or not cid:
                raise ConversationRepositoryError("Supabase returned an invalid conversation identity")
            result.append(cid)
        return result

    @staticmethod
    def _payload(snapshot: OwnedConversationSnapshot, owner_id: str) -> dict[str, Any]:
        record = snapshot.canonical_record
        return {
            "conversation_id": snapshot.conversation_id,
            "owner_id": owner_id,
            "canonical_record_json": _canonical_json(record),
            "snapshot_sha256": hashlib.sha256(_canonical_json(record).encode("utf-8")).hexdigest(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _update_existing(
        self,
        owner: AccountIdentity,
        owner_id: str,
        snapshot: OwnedConversationSnapshot,
        row: dict[str, Any],
    ) -> None:
        existing = self._decode_row(owner, owner_id, row)
        old_record = existing.canonical_record
        candidate_record = snapshot.canonical_record
        _assert_history_preserved(old_record, candidate_record)
        if old_record == candidate_record:
            return

        response = self._send(
            "PATCH",
            f"/rest/v1/{SUPABASE_TABLE}",
            params={
                "conversation_id": _eq_filter(snapshot.conversation_id),
                "owner_id": _eq_filter(owner_id),
            },
            payload={
                "canonical_record_json": _canonical_json(candidate_record),
                "snapshot_sha256": hashlib.sha256(_canonical_json(candidate_record).encode("utf-8")).hexdigest(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            prefer="return=representation",
        )
        rows = self._json(response, context="update")
        if not isinstance(rows, list) or not rows:
            raise ConversationOwnershipError(
                "conversation could not be updated for the authenticated owner"
            )

    def save(self, snapshot: OwnedConversationSnapshot) -> None:
        if not isinstance(snapshot, OwnedConversationSnapshot):
            raise ValueError("snapshot must be an OwnedConversationSnapshot")
        owner = snapshot.owner
        owner_id = self._assert_owner(owner)
        conversation_id = self._validate_conversation_id(snapshot.conversation_id)
        if conversation_id != snapshot.conversation_id:
            raise ValueError("snapshot conversation_id must already be normalized")

        existing = self._read_owned_row(owner, owner_id, conversation_id)
        if existing is not None:
            self._update_existing(owner, owner_id, snapshot, existing)
            return

        payload = self._payload(snapshot, owner_id)
        response = self._send(
            "POST",
            f"/rest/v1/{SUPABASE_TABLE}",
            payload=payload,
            prefer="return=representation",
        )
        status = int(getattr(response, "status_code", 0) or 0)
        if 200 <= status < 300:
            rows = self._json(response, context="save")
            if not isinstance(rows, list) or not rows:
                raise ConversationRepositoryError("Supabase did not confirm the conversation save")
            saved = rows[0]
            if not isinstance(saved, dict):
                raise ConversationRepositoryError("Supabase returned an invalid saved conversation")
            self._decode_row(owner, owner_id, saved)
            return

        if status == 409:
            # A concurrent insert or a globally colliding ID may win the race.
            # Re-read within the authenticated owner's RLS view. If the record
            # belongs to this owner, apply normal immutability checks; otherwise
            # return a generic ownership failure without exposing its existence.
            raced = self._read_owned_row(owner, owner_id, conversation_id)
            if raced is not None:
                self._update_existing(owner, owner_id, snapshot, raced)
                return
            raise ConversationOwnershipError(
                "conversation identifier is already bound or cannot be saved"
            )
        self._json(response, context="save")

    def delete(self, owner: AccountIdentity, conversation_id: str) -> bool:
        owner_id = self._assert_owner(owner)
        conversation_id = self._validate_conversation_id(conversation_id)
        response = self._send(
            "DELETE",
            f"/rest/v1/{SUPABASE_TABLE}",
            params={
                "conversation_id": _eq_filter(conversation_id),
                "owner_id": _eq_filter(owner_id),
                "select": "conversation_id",
            },
            prefer="return=representation",
        )
        rows = self._json(response, context="delete")
        if not isinstance(rows, list):
            raise ConversationRepositoryError("Supabase returned an invalid delete result")
        return any(
            isinstance(row, dict)
            and row.get("conversation_id") == conversation_id
            and row.get("owner_id") in (None, owner_id)
            for row in rows
        )
