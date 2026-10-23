"""Supabase/PostgREST adapter for owner-scoped canonical conversation snapshots.

This module deliberately is not imported by main.py or app.py. It requires a
verified Supabase Auth identity and that user's access JWT. The publishable key
identifies the project; PostgreSQL RLS and the signed JWT authorize every row.
Never pass a Supabase secret/service-role key to this adapter.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from typing import Any
from urllib.parse import urlsplit

import requests

from conversation_repository import (
    AccountIdentity,
    ConversationIdentityConflict,
    ConversationOwnershipError,
    ConversationRepositoryError,
    OwnedConversationSnapshot,
)

SUPABASE_CONVERSATION_SCHEMA = "ai-council-supabase-conversation/v1"
_TABLE = "council_conversations"
_IMMUTABLE_FIELDS = {
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
            "conversation_id", "session_id", "message_id", "request_id",
            "round", "round_number", "round_no", "ordinal", "round_ordinal",
            "canonical_round_base", "canonical_round_record_id",
            "canonical_identity_key", "created_at",
        ),
    ),
}


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _checksum(record: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(record).encode("utf-8")).hexdigest()


def _assert_history_preserved(previous: dict[str, Any], candidate: dict[str, Any]) -> None:
    """Mirror the database trigger's append-only identity fields as an early check."""
    for collection, (id_field, immutable_fields) in _IMMUTABLE_FIELDS.items():
        def rows_by_id(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
            rows = record.get(collection)
            if not isinstance(rows, list):
                raise ConversationRepositoryError("canonical identity collection is malformed")
            indexed: dict[str, dict[str, Any]] = {}
            for row in rows:
                if not isinstance(row, dict):
                    raise ConversationRepositoryError("canonical identity row is malformed")
                identity = str(row.get(id_field) or "").strip()
                if not identity:
                    raise ConversationRepositoryError("canonical identity ID is missing")
                if identity in indexed:
                    raise ConversationRepositoryError("duplicate canonical identity ID")
                indexed[identity] = row
            return indexed

        old_rows = rows_by_id(previous)
        new_rows = rows_by_id(candidate)
        if not set(old_rows).issubset(new_rows):
            raise ConversationIdentityConflict(
                f"canonical {collection} history cannot be silently removed"
            )
        for identity, old_row in old_rows.items():
            new_row = new_rows[identity]
            for field in immutable_fields:
                old_value = old_row.get(field)
                if old_value not in (None, "") and new_row.get(field) != old_value:
                    raise ConversationIdentityConflict(
                        f"canonical {collection} identity binding cannot be rewritten"
                    )


class SupabaseConversationRepository:
    """RLS-enforced Supabase adapter scoped to one authenticated session.

    Construct one adapter per verified signed-in Streamlit session. The
    access_token must be the short-lived user JWT from Supabase Auth, never a
    project secret/service-role key. Supabase verifies the JWT and auth.uid();
    this class binds its operations to one issuer + subject and refuses requests
    for any other AccountIdentity.

    Required migration:
      supabase/migrations/20261023000000_council_conversations.sql

    This adapter has not been wired into the production UI. A real two-account
    test must be run against a dedicated Supabase project before app integration.
    """

    def __init__(
        self,
        *,
        supabase_url: str,
        publishable_key: str,
        access_token: str,
        authenticated_identity: AccountIdentity,
        timeout_seconds: float = 10.0,
        session: Any | None = None,
    ) -> None:
        parsed = urlsplit(str(supabase_url or "").strip())
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("supabase_url must be an HTTPS project URL")
        if parsed.query or parsed.fragment or parsed.path not in ("", "/"):
            raise ValueError("supabase_url must be the project origin only")
        normalized_url = f"https://{parsed.netloc}".rstrip("/")
        if not isinstance(publishable_key, str) or not publishable_key.strip():
            raise ValueError("Supabase publishable key is required")
        if not isinstance(access_token, str) or not access_token.strip():
            raise ValueError("authenticated user's access token is required")
        if not isinstance(authenticated_identity, AccountIdentity):
            raise ValueError("authenticated_identity must be a verified AccountIdentity")
        if authenticated_identity.issuer != f"{normalized_url}/auth/v1":
            raise ValueError("identity issuer does not match the configured Supabase project")
        try:
            normalized_subject = str(uuid.UUID(authenticated_identity.subject))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("Supabase subject must be a UUID") from exc
        if normalized_subject != authenticated_identity.subject.lower():
            raise ValueError("Supabase subject UUID is not normalized")

        try:
            timeout = float(timeout_seconds)
        except (TypeError, ValueError) as exc:
            raise ValueError("timeout_seconds must be positive") from exc
        if timeout <= 0 or timeout > 60:
            raise ValueError("timeout_seconds must be between 0 and 60")

        self._base_url = normalized_url
        self._publishable_key = publishable_key.strip()
        self._access_token = access_token.strip()
        self._identity = authenticated_identity
        self._owner_id = normalized_subject
        self._timeout = timeout
        self._session = session if session is not None else requests.Session()

    def _assert_owner(self, owner: AccountIdentity) -> None:
        if not isinstance(owner, AccountIdentity) or owner != self._identity:
            raise ConversationOwnershipError(
                "repository session is not authorized for the requested account"
            )

    def _request(
        self,
        method: str,
        resource: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        prefer: str | None = None,
    ) -> Any:
        headers = {
            "apikey": self._publishable_key,
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        try:
            response = self._session.request(
                method,
                f"{self._base_url}/rest/v1/{resource}",
                params=params,
                json=payload,
                headers=headers,
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise ConversationRepositoryError(
                "Supabase storage is temporarily unavailable"
            ) from exc
        except Exception as exc:
            # Keep transport implementation details and credentials out of the UI/logs.
            raise ConversationRepositoryError(
                "Supabase storage request could not be completed"
            ) from exc

        status = int(getattr(response, "status_code", 0) or 0)
        if status < 200 or status >= 300:
            if status in (401, 403):
                raise ConversationRepositoryError(
                    "Supabase denied this request; the sign-in session may have expired"
                )
            if status in (409, 412):
                raise ConversationRepositoryError(
                    "Supabase rejected the conversation update"
                )
            raise ConversationRepositoryError(
                f"Supabase storage request failed (HTTP {status or 'unknown'})"
            )
        response_text = getattr(response, "text", None)
        if status == 204 or response_text == "":
            return []
        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ConversationRepositoryError(
                "Supabase returned an invalid storage response"
            ) from exc
        return data

    def _snapshot_from_row(
        self, row: Any, *, expected_conversation_id: str | None = None
    ) -> OwnedConversationSnapshot:
        if not isinstance(row, dict):
            raise ConversationRepositoryError("Supabase returned an invalid conversation row")
        conversation_id = row.get("conversation_id")
        owner_id = row.get("owner_id")
        record = row.get("canonical_record")
        checksum = row.get("checksum")
        if (
            row.get("schema") != SUPABASE_CONVERSATION_SCHEMA
            or not isinstance(conversation_id, str)
            or not conversation_id.strip()
            or not isinstance(owner_id, str)
            or owner_id.lower() != self._owner_id
            or not isinstance(record, dict)
            or not isinstance(checksum, str)
            or (expected_conversation_id is not None and conversation_id != expected_conversation_id)
        ):
            raise ConversationRepositoryError("Supabase conversation row failed validation")
        computed = _checksum(record)
        if not hmac.compare_digest(computed, checksum):
            raise ConversationRepositoryError("Supabase conversation checksum validation failed")
        try:
            return OwnedConversationSnapshot(self._identity, record)
        except (TypeError, ValueError) as exc:
            raise ConversationRepositoryError(
                "Supabase canonical conversation snapshot failed validation"
            ) from exc

    def save(self, snapshot: OwnedConversationSnapshot) -> None:
        if not isinstance(snapshot, OwnedConversationSnapshot):
            raise ValueError("snapshot must be an OwnedConversationSnapshot")
        self._assert_owner(snapshot.owner)
        record = snapshot.canonical_record
        conversation_id = snapshot.conversation_id

        # This read is an early user-friendly check only. The database trigger is
        # authoritative and repeats owner and immutable-history checks atomically.
        existing = self.load(snapshot.owner, conversation_id)
        if existing is not None:
            previous_record = existing.canonical_record
            if previous_record == record:
                return
            _assert_history_preserved(previous_record, record)

        payload = {
            "conversation_id": conversation_id,
            "owner_id": self._owner_id,
            "schema": SUPABASE_CONVERSATION_SCHEMA,
            "canonical_record": record,
            "checksum": _checksum(record),
        }
        response_rows = self._request(
            "POST",
            _TABLE,
            params={"on_conflict": "conversation_id"},
            payload=payload,
            prefer="resolution=merge-duplicates,return=representation",
        )
        if not isinstance(response_rows, list) or len(response_rows) != 1:
            # Empty representation may indicate a hidden cross-owner conflict.
            # Do not reveal whether another user owns the ID.
            raise ConversationRepositoryError(
                "Supabase did not confirm that the conversation was saved"
            )
        saved = self._snapshot_from_row(
            response_rows[0], expected_conversation_id=conversation_id
        )
        if saved.owner != snapshot.owner or saved.canonical_record != record:
            raise ConversationRepositoryError(
                "Supabase saved a snapshot different from the requested canonical record"
            )

    def load(
        self, owner: AccountIdentity, conversation_id: str
    ) -> OwnedConversationSnapshot | None:
        self._assert_owner(owner)
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            raise ValueError("conversation_id must be a non-empty string")
        wanted = conversation_id.strip()
        rows = self._request(
            "GET",
            _TABLE,
            params={
                "select": "conversation_id,owner_id,schema,canonical_record,checksum",
                "conversation_id": f"eq.{wanted}",
                "owner_id": f"eq.{self._owner_id}",
                "limit": "1",
            },
        )
        if not isinstance(rows, list):
            raise ConversationRepositoryError("Supabase returned an invalid conversation list")
        if not rows:
            return None
        if len(rows) != 1:
            raise ConversationRepositoryError("Supabase returned duplicate conversation rows")
        return self._snapshot_from_row(rows[0], expected_conversation_id=wanted)

    def list_ids(self, owner: AccountIdentity, *, limit: int = 50) -> list[str]:
        self._assert_owner(owner)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 500:
            raise ValueError("limit must be an integer between 1 and 500")
        rows = self._request(
            "GET",
            _TABLE,
            params={
                "select": "conversation_id",
                "owner_id": f"eq.{self._owner_id}",
                "order": "conversation_id.asc",
                "limit": str(limit),
            },
        )
        if not isinstance(rows, list):
            raise ConversationRepositoryError("Supabase returned an invalid conversation list")
        result: list[str] = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("conversation_id"), str):
                raise ConversationRepositoryError("Supabase returned an invalid conversation ID")
            result.append(row["conversation_id"])
        if len(result) != len(set(result)):
            raise ConversationRepositoryError("Supabase returned duplicate conversation IDs")
        return result

    def delete(self, owner: AccountIdentity, conversation_id: str) -> bool:
        self._assert_owner(owner)
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            raise ValueError("conversation_id must be a non-empty string")
        wanted = conversation_id.strip()
        deleted_rows = self._request(
            "DELETE",
            _TABLE,
            params={
                "conversation_id": f"eq.{wanted}",
                "owner_id": f"eq.{self._owner_id}",
                "select": "conversation_id,owner_id",
            },
            prefer="return=representation",
        )
        if not isinstance(deleted_rows, list):
            raise ConversationRepositoryError("Supabase returned an invalid delete response")
        if not deleted_rows:
            return False
        if len(deleted_rows) != 1:
            raise ConversationRepositoryError("Supabase returned duplicate deleted rows")
        row = deleted_rows[0]
        if not isinstance(row, dict) or row.get("owner_id", "").lower() != self._owner_id:
            raise ConversationRepositoryError("Supabase delete response failed owner validation")
        return True
