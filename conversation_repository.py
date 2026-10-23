"""Ownership-aware repository contract for canonical AI Council conversations.

This module defines the boundary for a future durable storage adapter. It does
not authenticate users and does not provide durable storage itself. Callers
must derive AccountIdentity from a verified authentication flow. Production
adapters must enforce ownership in the storage/query policy layer.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

CANONICAL_STORE_CONTRACT = "V26_3_CANONICAL_CONVERSATION_STORE"
_CANONICAL_COLLECTIONS = ("messages", "requests", "rounds")
_ID_FIELDS = {"messages": "message_id", "requests": "request_id", "rounds": "round_id"}


class ConversationRepositoryError(RuntimeError):
    """Base class for safe, expected repository failures."""


class ConversationAuthenticationError(ConversationRepositoryError):
    """Raised when the configured Supabase access token is not authenticated."""


class ConversationOwnershipError(ConversationRepositoryError):
    """Raised when a write would cross an established conversation owner."""


class ConversationIdentityConflict(ConversationRepositoryError):
    """Raised when a stored canonical identity would be rewritten or removed."""


@dataclass(frozen=True)
class AccountIdentity:
    """Stable identity from a verified issuer; subject values are opaque.

    The identity adapter must validate the issuer and sign-in result before
    constructing this object. Values are trimmed but never lowercased because
    subject identifiers are issuer-defined and case-sensitive.
    """

    issuer: str
    subject: str

    def __post_init__(self) -> None:
        for name, maximum in (("issuer", 2048), ("subject", 1024)):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise ValueError(f"{name} must be a string")
            value = value.strip()
            if not value:
                raise ValueError(f"{name} must not be empty")
            if len(value) > maximum:
                raise ValueError(f"{name} exceeds the supported length")
            if any(ord(char) < 32 or ord(char) == 127 for char in value):
                raise ValueError(f"{name} must not contain control characters")
            object.__setattr__(self, name, value)

    @property
    def key(self) -> tuple[str, str]:
        """Opaque composite key; do not replace it with email or display name."""
        return (self.issuer, self.subject)


def _validate_canonical_references(
    canonical_record: dict[str, Any],
    conversation_id: str,
    rows_by_collection: dict[str, dict[str, dict[str, Any]]],
) -> None:
    """Reject cross-conversation rows and dangling or contradictory identity edges.

    A durable snapshot may contain a partial lifecycle (for example before the
    first Round exists), but every identity edge that is present must resolve.
    User Messages, Requests, and Rounds must retain their canonical bindings.
    """
    for collection in _CANONICAL_COLLECTIONS:
        for row in rows_by_collection[collection].values():
            row_conversation_id = row.get("conversation_id")
            if row_conversation_id not in (None, ""):
                if not isinstance(row_conversation_id, str) or row_conversation_id.strip() != conversation_id:
                    raise ValueError(f"canonical {collection} row belongs to another conversation")

    messages = rows_by_collection["messages"]
    requests = rows_by_collection["requests"]
    rounds = rows_by_collection["rounds"]

    # Check direct request-to-message references first so a dangling edge is
    # reported as such, rather than as a secondary reverse-link mismatch.
    for request in requests.values():
        message_id = str(request.get("message_id") or "").strip()
        if not message_id or message_id not in messages:
            raise ValueError("canonical request references a missing message")

    for message_id, message in messages.items():
        request_id = str(message.get("request_id") or "").strip()
        is_user_message = str(message.get("role") or "").strip().lower() == "user"
        if is_user_message and not request_id:
            raise ValueError("canonical user message is missing its request binding")
        if request_id and request_id not in requests:
            raise ValueError("canonical message references a missing request")
        if is_user_message:
            request = requests[request_id]
            if str(request.get("message_id") or "").strip() != message_id:
                raise ValueError("canonical user message/request binding mismatch")

    for request_id, request in requests.items():
        message_id = str(request.get("message_id") or "").strip()
        message = messages[message_id]
        if str(message.get("role") or "").strip().lower() == "user":
            if str(message.get("request_id") or "").strip() != request_id:
                raise ValueError("canonical request/message binding mismatch")

    for round_id, round_row in rounds.items():
        request_id = str(round_row.get("request_id") or "").strip()
        message_id = str(round_row.get("message_id") or "").strip()
        if not request_id or request_id not in requests:
            raise ValueError("canonical round references a missing request")
        if not message_id or message_id not in messages:
            raise ValueError("canonical round references a missing message")
        request = requests[request_id]
        if str(request.get("message_id") or "").strip() != message_id:
            raise ValueError("canonical round/request message binding mismatch")


@dataclass(frozen=True, init=False)
class OwnedConversationSnapshot:
    """Defensive JSON-compatible envelope around one canonical snapshot.

    The owner is stored separately from the canonical conversation record.
    Access to canonical_record returns a fresh dictionary, so callers cannot
    mutate the envelope by retaining a reference to an input mapping.
    """

    owner: AccountIdentity
    conversation_id: str
    _record_json: str = field(repr=False)

    def __init__(self, owner: AccountIdentity, canonical_record: dict[str, Any]) -> None:
        if not isinstance(owner, AccountIdentity):
            raise ValueError("owner must be a verified AccountIdentity")
        if not isinstance(canonical_record, dict):
            raise ValueError("canonical_record must be a dictionary")

        raw_conversation_id = canonical_record.get("conversation_id")
        if not isinstance(raw_conversation_id, str):
            raise ValueError("canonical snapshot has no valid conversation_id")
        conversation_id = raw_conversation_id.strip()
        if (
            not conversation_id
            or conversation_id != raw_conversation_id
            or len(conversation_id) > 1024
            or any(ord(char) < 32 or ord(char) == 127 for char in conversation_id)
        ):
            raise ValueError("canonical snapshot has no valid conversation_id")
        if canonical_record.get("canonical_store_contract") != CANONICAL_STORE_CONTRACT:
            raise ValueError("snapshot is not from the canonical conversation store")

        rows_by_collection: dict[str, dict[str, dict[str, Any]]] = {}
        for collection in _CANONICAL_COLLECTIONS:
            rows = canonical_record.get(collection)
            if not isinstance(rows, list):
                raise ValueError(f"canonical {collection} must be a list")
            identity_field = _ID_FIELDS[collection]
            by_id: dict[str, dict[str, Any]] = {}
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError(f"canonical {collection} entries must be dictionaries")
                raw_identity = row.get(identity_field)
                if not isinstance(raw_identity, str):
                    raise ValueError(f"canonical {collection} entry has no {identity_field}")
                identity = raw_identity.strip()
                if not identity or identity != raw_identity:
                    raise ValueError(f"canonical {collection} entry has no valid {identity_field}")
                if any(ord(char) < 32 or ord(char) == 127 for char in identity):
                    raise ValueError(f"canonical {collection} entry has an invalid {identity_field}")
                if identity in by_id:
                    raise ValueError(f"duplicate canonical {identity_field}")
                by_id[identity] = row
            rows_by_collection[collection] = by_id

        _validate_canonical_references(canonical_record, conversation_id, rows_by_collection)

        try:
            frozen_json = json.dumps(
                canonical_record,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("canonical snapshot must contain JSON-compatible data") from exc

        object.__setattr__(self, "owner", owner)
        object.__setattr__(self, "conversation_id", conversation_id)
        object.__setattr__(self, "_record_json", frozen_json)

    @property
    def canonical_record(self) -> dict[str, Any]:
        """Return a defensive copy suitable for adapter-specific serialization."""
        return json.loads(self._record_json)


@runtime_checkable
class ConversationRepository(Protocol):
    """Required API for durable adapters.

    save must be atomic and idempotent for an unchanged snapshot. An existing
    conversation cannot silently change owners; immutable Message/Request/Round
    identities cannot be rewritten or erased. Every read/list/delete operation
    must be scoped to the supplied verified owner. load returns None and delete
    returns False for missing and unowned IDs, avoiding an existence oracle.
    Production ownership enforcement belongs in the storage/query policy layer.
    """

    def save(self, snapshot: OwnedConversationSnapshot) -> None:
        """Persist a snapshot under its verified owner or fail closed."""
        ...

    def load(self, owner: AccountIdentity, conversation_id: str) -> OwnedConversationSnapshot | None:
        """Return an owned snapshot only; do not disclose another owner's data."""
        ...

    def list_ids(self, owner: AccountIdentity, *, limit: int = 50) -> list[str]:
        """List only IDs owned by the supplied identity."""
        ...

    def delete(self, owner: AccountIdentity, conversation_id: str) -> bool:
        """Delete an owned snapshot; return False for missing or unowned IDs."""
        ...
