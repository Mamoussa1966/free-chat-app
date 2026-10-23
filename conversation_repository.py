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

        conversation_id = str(canonical_record.get("conversation_id") or "").strip()
        if not conversation_id:
            raise ValueError("canonical snapshot has no conversation_id")
        if canonical_record.get("canonical_store_contract") != CANONICAL_STORE_CONTRACT:
            raise ValueError("snapshot is not from the canonical conversation store")

        for collection in _CANONICAL_COLLECTIONS:
            rows = canonical_record.get(collection)
            if not isinstance(rows, list):
                raise ValueError(f"canonical {collection} must be a list")
            identity_field = _ID_FIELDS[collection]
            seen: set[str] = set()
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError(f"canonical {collection} entries must be dictionaries")
                identity = str(row.get(identity_field) or "").strip()
                if identity and identity in seen:
                    raise ValueError(f"duplicate canonical {identity_field}")
                if identity:
                    seen.add(identity)

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
