from __future__ import annotations

import copy
import json
from typing import Any

from backup_engine import BACKUP_SCHEMA, verify_conversation_backup
from conversation_repository import (
    CANONICAL_STORE_CONTRACT,
    AccountIdentity,
    ConversationRepositoryError,
    OwnedConversationSnapshot,
)


MAX_RESTORE_CONVERSATIONS = 500
_PRESENTATION_KEYS = {
    "title",
    "created_at",
    "messages",
    "request_records",
    "request_ids",
    "history_identity_ledger",
    "result_keys",
    "bridge_ledger_v24",
}


class BackupRestoreError(ValueError):
    """A supplied backup cannot be restored without violating the safety contract."""


def _presentation_projection(item: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    supplied = item.get("stored_presentation_state")
    if isinstance(supplied, dict):
        view = {
            key: copy.deepcopy(value)
            for key, value in supplied.items()
            if key in _PRESENTATION_KEYS
        }
    else:
        # Older/session-only exports did not necessarily include a separate
        # presentation projection. Rebuild only a conservative display shell
        # from the exported message/Request identities.
        messages = snapshot.get("messages")
        requests = snapshot.get("requests")
        bridges = snapshot.get("bridges")
        view = {
            "messages": copy.deepcopy(messages if isinstance(messages, list) else []),
            "request_records": [],
            "request_ids": [
                str(row.get("request_id"))
                for row in (requests if isinstance(requests, list) else [])
                if isinstance(row, dict) and row.get("request_id")
            ],
            "history_identity_ledger": [],
            "result_keys": [],
            "bridge_ledger_v24": copy.deepcopy(bridges if isinstance(bridges, list) else []),
        }

    view.setdefault("title", "محادثة مستعادة")
    view.setdefault("created_at", str(snapshot.get("created_at") or ""))
    # This projection is bounded to the same UI caps used by the live app.
    for key, limit in (
        ("messages", 200),
        ("request_records", 50),
        ("request_ids", 50),
        ("history_identity_ledger", 2000),
        ("result_keys", 2000),
        ("bridge_ledger_v24", 50),
    ):
        value = view.get(key, [])
        if not isinstance(value, list):
            raise BackupRestoreError(f"presentation field {key} must be a list")
        view[key] = copy.deepcopy(value[-limit:])
    view["title"] = str(view.get("title") or "محادثة مستعادة")[:80]
    view["created_at"] = str(view.get("created_at") or "")[:100]
    try:
        json.dumps(view, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise BackupRestoreError("presentation data is not valid JSON") from exc
    return view


def build_restore_snapshots(
    document: dict[str, Any],
    owner: AccountIdentity,
) -> list[OwnedConversationSnapshot]:
    """Validate the entire export and construct owner-bound immutable snapshots.

    No database reads/writes happen here. All conversations are fully validated
    before callers are allowed to start a restore operation.
    """
    if not isinstance(owner, AccountIdentity):
        raise BackupRestoreError("a verified authenticated owner is required")
    if not isinstance(document, dict) or document.get("schema") != BACKUP_SCHEMA:
        raise BackupRestoreError("unsupported backup format")
    if not verify_conversation_backup(document):
        raise BackupRestoreError("backup integrity or canonical-history verification failed")

    conversations = document.get("conversations")
    if (
        not isinstance(conversations, list)
        or len(conversations) > MAX_RESTORE_CONVERSATIONS
        or document.get("conversation_count") != len(conversations)
    ):
        raise BackupRestoreError("backup conversation count is invalid")

    snapshots: list[OwnedConversationSnapshot] = []
    seen: set[str] = set()
    for item in conversations:
        if not isinstance(item, dict):
            raise BackupRestoreError("backup contains a malformed conversation")
        conversation_id = str(item.get("conversation_id") or "").strip()
        exported = item.get("snapshot")
        if not conversation_id or conversation_id in seen or not isinstance(exported, dict):
            raise BackupRestoreError("backup contains a missing or duplicate conversation identity")
        seen.add(conversation_id)
        canonical = exported.get("canonical_conversation_record")
        if not isinstance(canonical, dict):
            raise BackupRestoreError("canonical conversation history is missing")
        messages, requests, rounds = (
            canonical.get("messages"),
            canonical.get("requests"),
            canonical.get("rounds"),
        )
        if not all(isinstance(rows, list) for rows in (messages, requests, rounds)):
            raise BackupRestoreError("canonical Message/Request/Round collections are malformed")

        record = {
            "conversation_id": conversation_id,
            "session_id": str(exported.get("session_id") or ""),
            "canonical_store_contract": CANONICAL_STORE_CONTRACT,
            "canonical_store_committed": True,
            "messages": copy.deepcopy(messages),
            "requests": copy.deepcopy(requests),
            "rounds": copy.deepcopy(rounds),
        }
        record["_streamlit_state"] = _presentation_projection(item, exported)
        try:
            snapshots.append(OwnedConversationSnapshot(owner, record))
        except (TypeError, ValueError) as exc:
            raise BackupRestoreError(
                f"canonical snapshot validation failed for conversation {conversation_id}"
            ) from exc

    return snapshots


def restore_only_missing_conversations(
    document: dict[str, Any],
    *,
    owner: AccountIdentity,
    repository: Any,
) -> dict[str, Any]:
    """Insert missing owner-scoped snapshots without ever updating existing IDs.

    The repository must expose an atomic restore_if_absent method. A normal
    upsert/save API is deliberately not accepted because a race could overwrite
    a conversation created after a preflight read.
    """
    snapshots = build_restore_snapshots(document, owner)
    restore_method = getattr(repository, "restore_if_absent", None)
    if not callable(restore_method):
        raise BackupRestoreError("repository does not support atomic insert-only restore")

    restored = 0
    skipped_existing = 0
    failed: list[str] = []
    for snapshot in snapshots:
        try:
            inserted = restore_method(snapshot)
        except ConversationRepositoryError:
            failed.append(snapshot.conversation_id)
            break
        except Exception:
            failed.append(snapshot.conversation_id)
            break
        if inserted is True:
            restored += 1
        elif inserted is False:
            skipped_existing += 1
        else:
            failed.append(snapshot.conversation_id)
            break

    return {
        "status": "PARTIAL" if failed else "COMPLETED",
        "total": len(snapshots),
        "restored": restored,
        "skipped_existing": skipped_existing,
        "failed_conversation_ids": failed,
        "writes_are_insert_only": True,
        "provider_api_calls": 0,
        "existing_conversations_overwritten": 0,
    }
