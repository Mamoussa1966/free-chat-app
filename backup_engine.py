from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from conversation_store import authoritative_snapshot, canonical_history_hash


BACKUP_SCHEMA = "ai-council-canonical-backup/v1"
MAX_BACKUP_CONVERSATIONS = 500
MAX_BACKUP_JSON_BYTES = 25 * 1024 * 1024


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def build_conversation_backup(
    chats: list[dict],
    *,
    source: str = "streamlit_session",
    possible_truncation: bool = False,
    exported_at: str | None = None,
) -> dict[str, Any]:
    """Build a read-only, checksummed export of canonical conversation records.

    The input chat dictionaries are deep-copied before snapshot projection.
    Binary uploads/voice blobs, provider credentials, and external account
    secrets are not included. User-entered text is preserved as conversation
    content and may itself contain sensitive information.
    """
    if not isinstance(chats, list):
        raise ValueError("chats must be a list")
    if len(chats) > MAX_BACKUP_CONVERSATIONS:
        raise ValueError(
            f"backup is limited to {MAX_BACKUP_CONVERSATIONS} conversations per export"
        )

    timestamp = str(exported_at or "").strip()
    if not timestamp:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    safe_source = str(source or "unknown").strip()[:80]
    conversations: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for chat in chats:
        if not isinstance(chat, dict):
            raise ValueError("a conversation entry is malformed")
        working_copy = copy.deepcopy(chat)
        conversation_id = str(working_copy.get("conversation_id") or "").strip()
        if not conversation_id:
            raise ValueError("a conversation is missing its canonical conversation_id")
        if conversation_id in seen_ids:
            raise ValueError("duplicate conversation_id found in backup input")
        seen_ids.add(conversation_id)

        snapshot = authoritative_snapshot(working_copy)
        canonical_record = snapshot.get("canonical_conversation_record")
        if not isinstance(canonical_record, dict):
            raise ValueError("canonical conversation record is missing")
        if str(snapshot.get("conversation_id") or "").strip() != conversation_id:
            raise ValueError("canonical conversation identity does not match the source row")

        conversation_export = {
            "conversation_id": conversation_id,
            "canonical_history_sha256": canonical_history_hash(canonical_record),
            "snapshot": snapshot,
        }
        # Supabase also stores a separately sanitized Streamlit presentation
        # projection (message text, compact request history, and result keys).
        # Preserve that exact stored projection when exporting a remote backup;
        # it is not recreated from incomplete compatibility ledgers.
        presentation_state = working_copy.get("_backup_presentation_state")
        if isinstance(presentation_state, dict):
            conversation_export["stored_presentation_state"] = copy.deepcopy(presentation_state)
        conversations.append(conversation_export)

    conversations.sort(key=lambda row: row["conversation_id"])
    document: dict[str, Any] = {
        "schema": BACKUP_SCHEMA,
        "exported_at": timestamp,
        "source": safe_source,
        "conversation_count": len(conversations),
        "limits": {
            "maximum_conversations_per_export": MAX_BACKUP_CONVERSATIONS,
            "possible_truncation": bool(possible_truncation),
        },
        "media": {
            "binary_attachments_included": False,
            "voice_recording_blobs_included": False,
        },
        "secrets": {
            "provider_credentials_from_application_settings_included": False,
            "user_entered_sensitive_text_may_be_present": True,
        },
        "restore": {
            "automatic_restore_supported": False,
            "meaning": "Export-only snapshot. Import/restore requires a separately reviewed migration path.",
        },
        "conversations": conversations,
    }
    digest = hashlib.sha256(_canonical_json(document).encode("utf-8")).hexdigest()
    document["integrity"] = {
        "algorithm": "SHA-256",
        "payload_sha256": digest,
    }
    encoded_size = len(serialize_conversation_backup(document).encode("utf-8"))
    if encoded_size > MAX_BACKUP_JSON_BYTES:
        raise ValueError(
            f"backup exceeds the {MAX_BACKUP_JSON_BYTES // (1024 * 1024)} MB export limit"
        )
    return document


def serialize_conversation_backup(document: dict[str, Any]) -> str:
    """Serialize a backup bundle to portable UTF-8 JSON."""
    if not isinstance(document, dict) or document.get("schema") != BACKUP_SCHEMA:
        raise ValueError("unsupported backup document")
    return json.dumps(
        document,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    )


def verify_conversation_backup(document: dict[str, Any]) -> bool:
    """Verify bundle integrity, metadata, identities, and every canonical-history digest.

    This is an integrity check, not a digital signature or proof of who created
    the file. It performs no storage writes and never mutates the supplied data.
    """
    if not isinstance(document, dict) or document.get("schema") != BACKUP_SCHEMA:
        return False

    try:
        # Reject malformed/unbounded documents before trusting any nested field.
        serialized = serialize_conversation_backup(document)
        if len(serialized.encode("utf-8")) > MAX_BACKUP_JSON_BYTES:
            return False

        integrity = document.get("integrity")
        if not isinstance(integrity, dict) or integrity.get("algorithm") != "SHA-256":
            return False
        expected = integrity.get("payload_sha256")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            return False
        payload = {key: value for key, value in document.items() if key != "integrity"}
        actual = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
        if not __import__("hmac").compare_digest(actual, expected):
            return False

        exported_at = document.get("exported_at")
        source = document.get("source")
        if not isinstance(exported_at, str) or not exported_at.strip():
            return False
        if not isinstance(source, str) or not source.strip() or len(source) > 80:
            return False

        conversations = document.get("conversations")
        count = document.get("conversation_count")
        if (
            not isinstance(conversations, list)
            or not isinstance(count, int)
            or isinstance(count, bool)
            or count != len(conversations)
            or count > MAX_BACKUP_CONVERSATIONS
        ):
            return False

        limits = document.get("limits")
        if (
            not isinstance(limits, dict)
            or limits.get("maximum_conversations_per_export") != MAX_BACKUP_CONVERSATIONS
            or not isinstance(limits.get("possible_truncation"), bool)
        ):
            return False

        media = document.get("media")
        secrets = document.get("secrets")
        restore = document.get("restore")
        if (
            not isinstance(media, dict)
            or media.get("binary_attachments_included") is not False
            or media.get("voice_recording_blobs_included") is not False
            or not isinstance(secrets, dict)
            or secrets.get("provider_credentials_from_application_settings_included") is not False
            or secrets.get("user_entered_sensitive_text_may_be_present") is not True
            or not isinstance(restore, dict)
            or restore.get("automatic_restore_supported") is not False
        ):
            return False

        seen_ids: set[str] = set()
        for item in conversations:
            if not isinstance(item, dict):
                return False
            conversation_id = item.get("conversation_id")
            if (
                not isinstance(conversation_id, str)
                or not conversation_id.strip()
                or conversation_id != conversation_id.strip()
                or conversation_id in seen_ids
            ):
                return False
            seen_ids.add(conversation_id)

            snapshot = item.get("snapshot")
            if not isinstance(snapshot, dict) or snapshot.get("conversation_id") != conversation_id:
                return False
            canonical_record = snapshot.get("canonical_conversation_record")
            if (
                not isinstance(canonical_record, dict)
                or canonical_record.get("conversation_id") != conversation_id
            ):
                return False
            for collection in ("messages", "requests", "rounds"):
                rows = canonical_record.get(collection)
                if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                    return False

            per_conversation_digest = item.get("canonical_history_sha256")
            if (
                not isinstance(per_conversation_digest, str)
                or not re.fullmatch(r"[0-9a-f]{64}", per_conversation_digest)
            ):
                return False
            if not __import__("hmac").compare_digest(
                canonical_history_hash(canonical_record),
                per_conversation_digest,
            ):
                return False

            presentation = item.get("stored_presentation_state")
            if presentation is not None and not isinstance(presentation, dict):
                return False

        return True
    except (TypeError, ValueError, UnicodeEncodeError, OverflowError):
        return False
