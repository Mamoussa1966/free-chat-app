from __future__ import annotations
import copy
from datetime import datetime, timezone
from conversation_schema import SCHEMA_VERSION

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

def ensure_store(chat: dict) -> dict:
    chat.setdefault("conversation_store_schema", SCHEMA_VERSION)
    chat.setdefault("conversation_record", {})
    chat.setdefault("message_ledger_v24", [])
    chat.setdefault("round_ledger_v24", [])
    chat.setdefault("request_ledger_v24", [])
    chat.setdefault("bridge_ledger_v24", [])
    chat.setdefault("result_ledger_v24", [])
    chat.setdefault("provenance_ledger_v24", [])
    chat.setdefault("timeline_ledger_v24", [])
    chat.setdefault("memory_l0", {})
    chat.setdefault("memory_l1", {"message_ids": [], "context_digest": ""})
    chat.setdefault("memory_l2", {"items": []})
    chat.setdefault("memory_l3", {})
    chat.setdefault("archived", False)
    chat.setdefault("updated_at_v24", now())
    chat.setdefault("v25_schema", "v25-conversation-ledger-message-runtime/v1")
    chat.setdefault("request_ledger_v25", [])
    chat.setdefault("round_ledger_v25", [])
    chat.setdefault("message_synthesis_ledger_v25", [])
    chat.setdefault("v25_authoritative_audit", {})
    return chat

def touch(chat: dict) -> None:
    ensure_store(chat)
    chat["updated_at_v24"] = now()
    rec = chat["conversation_record"]
    rec.update({"conversation_id": chat.get("conversation_id"), "session_id": chat.get("session_id"), "created_at": rec.get("created_at") or chat.get("created_at") or now(), "updated_at": chat["updated_at_v24"]})

def append_once(rows: list, row: dict, identity_keys: tuple[str, ...]) -> None:
    ident = tuple(str(row.get(k, "")) for k in identity_keys)
    if not all(ident):
        raise ValueError("ledger identity is incomplete")
    for old in rows:
        if tuple(str(old.get(k, "")) for k in identity_keys) == ident:
            return
    rows.append(copy.deepcopy(row))

def authoritative_snapshot(chat: dict) -> dict:
    ensure_store(chat)
    return {
        "schema": SCHEMA_VERSION,
        "conversation_id": chat.get("conversation_id"),
        "session_id": chat.get("session_id"),
        "messages": copy.deepcopy(chat.get("message_ledger_v24", [])),
        "rounds": copy.deepcopy(chat.get("round_ledger_v24", [])),
        "requests": copy.deepcopy(chat.get("request_ledger_v24", [])),
        "bridges": copy.deepcopy(chat.get("bridge_ledger_v24", [])),
        "results": copy.deepcopy(chat.get("result_ledger_v24", [])),
        "provenance": copy.deepcopy(chat.get("provenance_ledger_v24", [])),
        "timeline": copy.deepcopy(chat.get("timeline_ledger_v24", [])),
        "memory": {"L0": copy.deepcopy(chat.get("memory_l0", {})), "L1": copy.deepcopy(chat.get("memory_l1", {})), "L2": copy.deepcopy(chat.get("memory_l2", {})), "L3": copy.deepcopy(chat.get("memory_l3", {}))},
    }
