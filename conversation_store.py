from __future__ import annotations
import copy
from datetime import datetime, timezone
from conversation_schema import SCHEMA_VERSION

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

def ensure_store(chat: dict) -> dict:
    chat.setdefault("conversation_store_schema", SCHEMA_VERSION)
    chat.setdefault("conversation_record", {})
    # V26.3.5: HOTFIX145 ConversationRecord itself is the canonical historical
    # container.  The V26 persistence bucket is a compatibility/schema view of
    # the same lists, never a separate audit-only ledger.
    rec = chat.get("conversation_record")
    if not isinstance(rec, dict):
        rec = {}
        chat["conversation_record"] = rec
    rec.setdefault("messages", [])
    rec.setdefault("requests", [])
    rec.setdefault("rounds", [])
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
    chat.setdefault("message_ledger_v26", [])
    chat.setdefault("v26_authoritative_audit", {})
    return chat

def touch(chat: dict) -> None:
    ensure_store(chat)
    chat["updated_at_v24"] = now()
    rec = chat["conversation_record"]
    rec.update({"conversation_id": chat.get("conversation_id"), "session_id": chat.get("session_id"), "created_at": rec.get("created_at") or chat.get("created_at") or now(), "updated_at": chat["updated_at_v24"]})

def _canonical_record(chat: dict) -> dict:
    """Return the single canonical ConversationRecord container."""
    ensure_store(chat)
    rec = chat["conversation_record"]
    rec.setdefault("messages", [])
    rec.setdefault("requests", [])
    rec.setdefault("rounds", [])
    return rec

def commit_canonical_record(chat: dict, session_state=None) -> dict:
    """Commit the complete canonical ConversationRecord at a lifecycle boundary.

    The chat ConversationRecord remains authoritative. Session State is only the
    transport backing used to survive Streamlit script reruns; it is a deep-copy
    checkpoint of the complete record, never a current-request audit source.
    """
    rec = _canonical_record(chat)
    cid = str(chat.get("conversation_id") or "").strip()
    if not cid:
        return rec
    touch(chat)
    if session_state is not None:
        root = session_state.setdefault("v26_3_canonical_conversation_store", {})
        if not isinstance(root, dict):
            root = {}
            session_state["v26_3_canonical_conversation_store"] = root
        existing = root.get(cid) if isinstance(root.get(cid), dict) else None
        # V26.3.10: COMMIT is monotonic. A narrowed/current runtime object may
        # never overwrite an already committed historical ConversationRecord.
        # Merge the previously committed record into the current record first,
        # then publish the union as the new canonical snapshot.
        if existing and isinstance(existing.get("record"), dict):
            saved = existing["record"]
            for key, ident in (("messages", "message_id"), ("requests", "request_id"), ("rounds", "round_id")):
                target = rec.setdefault(key, [])
                by_id = {str(x.get(ident) or ""): x for x in target if isinstance(x, dict) and str(x.get(ident) or "")}
                incoming = saved.get(key, []) if isinstance(saved.get(key), list) else []
                for item in incoming:
                    if not isinstance(item, dict):
                        continue
                    iid = str(item.get(ident) or "")
                    if not iid:
                        continue
                    old = by_id.get(iid)
                    if old is None:
                        target.append(copy.deepcopy(item))
                        by_id[iid] = target[-1]
                    else:
                        for k, v in item.items():
                            if v not in (None, "", [], {}):
                                old[k] = copy.deepcopy(v)
            _chat_rebind_alias(chat)
        root[cid] = copy.deepcopy({
            "schema": "v26.3.11-canonical-conversation-store/v9",
            "conversation_id": cid,
            "session_id": str(chat.get("session_id") or ""),
            "record": copy.deepcopy(rec),
        })
    return rec

def hydrate_canonical_record(chat: dict, session_state=None) -> dict:
    """Restore the complete canonical ConversationRecord before runtime/audit use."""
    ensure_store(chat)
    cid = str(chat.get("conversation_id") or "").strip()
    if not cid or session_state is None:
        return chat
    root = session_state.get("v26_3_canonical_conversation_store", {})
    saved = root.get(cid) if isinstance(root, dict) else None
    if not isinstance(saved, dict) or not isinstance(saved.get("record"), dict):
        return chat
    saved_record = saved["record"]
    current = chat["conversation_record"]
    # Never replace canonical history with a narrower/current record. Merge by
    # immutable identity and preserve explicit conflicts.
    for key, ident in (("messages", "message_id"), ("requests", "request_id"), ("rounds", "round_id")):
        target = current.setdefault(key, [])
        existing = {str(x.get(ident) or ""): x for x in target if isinstance(x, dict) and str(x.get(ident) or "")}
        for item in saved_record.get(key, []) if isinstance(saved_record.get(key), list) else []:
            if not isinstance(item, dict):
                continue
            iid = str(item.get(ident) or "")
            if not iid:
                continue
            old = existing.get(iid)
            if old is None:
                target.append(copy.deepcopy(item))
                existing[iid] = target[-1]
            else:
                for k, v in item.items():
                    if v not in (None, "", [], {}):
                        old[k] = copy.deepcopy(v)
    _chat_rebind_alias(chat)
    return chat

def _chat_rebind_alias(chat: dict) -> None:
    rec = _canonical_record(chat)
    root = rec.setdefault("v26_3_conversation_persistence", {})
    if not isinstance(root, dict):
        root = {}
        rec["v26_3_conversation_persistence"] = root
    cid = str(chat.get("conversation_id") or "").strip()
    if cid:
        row = root.setdefault(cid, {})
        row.update({"schema": "v26.3.8-canonical-conversation-store/v7", "conversation_id": cid,
                    "messages": rec["messages"], "requests": rec["requests"], "rounds": rec["rounds"]})
    chat["v26_3_conversation_persistence"] = root



def rebuild_runtime_indexes_from_canonical(chat: dict, session_state=None) -> dict:
    """Rebuild compatibility/runtime indexes strictly from the hydrated canonical record.

    This is an index rebuild, not a second persistence source and not an audit
    reconstruction. The canonical ConversationRecord remains the sole historical
    owner of Message/Request/Round identity.
    """
    hydrate_canonical_record(chat, session_state)
    rec = _canonical_record(chat)

    def merge_by_id(rows, incoming, ident):
        if not isinstance(rows, list):
            rows = []
        by_id = {str(x.get(ident) or ""): x for x in rows if isinstance(x, dict) and str(x.get(ident) or "")}
        for item in incoming:
            if not isinstance(item, dict):
                continue
            iid = str(item.get(ident) or "").strip()
            if not iid:
                continue
            old = by_id.get(iid)
            if old is None:
                rows.append(copy.deepcopy(item))
                by_id[iid] = rows[-1]
            else:
                for k, v in item.items():
                    if v not in (None, "", [], {}):
                        old[k] = copy.deepcopy(v)
        return rows

    chat["message_ledger"] = merge_by_id(chat.get("message_ledger", []), rec.get("messages", []), "message_id")
    chat["request_records"] = merge_by_id(chat.get("request_records", []), rec.get("requests", []), "request_id")
    chat["round_ledger"] = merge_by_id(chat.get("round_ledger", []), rec.get("rounds", []), "round_id")
    # Keep the bounded compatibility ledgers aligned without becoming historical
    # authority. These are indexes only; audit reads the canonical record.
    chat["message_ledger"] = chat["message_ledger"][-1000:]
    chat["request_records"] = chat["request_records"][-1000:]
    chat["round_ledger"] = chat["round_ledger"][-2000:]
    return chat

def canonical_upsert_message(chat: dict, message: dict, session_state=None) -> dict:
    """Create/update a MessageRecord in the canonical ConversationRecord before dispatch."""
    rec = _canonical_record(chat)
    mid = str(message.get("message_id") or message.get("id") or "").strip()
    if not mid:
        raise ValueError("canonical MessageRecord requires message_id")
    row = dict(message)
    row["message_id"] = mid
    existing = next((x for x in rec["messages"] if isinstance(x, dict) and str(x.get("message_id") or "") == mid), None)
    if existing is None:
        rec["messages"].append(copy.deepcopy(row))
        existing = rec["messages"][-1]
    else:
        for k, v in row.items():
            if v not in (None, "", [], {}):
                existing[k] = copy.deepcopy(v)
    commit_canonical_record(chat, session_state)
    return existing


def canonical_upsert_request(chat: dict, request: dict, session_state=None) -> dict:
    """Create/update a RequestRecord in the canonical ConversationRecord before dispatch."""
    rec = _canonical_record(chat)
    rid = str(request.get("request_id") or "").strip()
    if not rid:
        raise ValueError("canonical RequestRecord requires request_id")
    row = dict(request)
    row["request_id"] = rid
    existing = next((x for x in rec["requests"] if isinstance(x, dict) and str(x.get("request_id") or "") == rid), None)
    if existing is None:
        rec["requests"].append(copy.deepcopy(row))
        existing = rec["requests"][-1]
    else:
        for k, v in row.items():
            if v not in (None, "", [], {}):
                existing[k] = copy.deepcopy(v)
    commit_canonical_record(chat, session_state)
    return existing


def canonical_upsert_round(chat: dict, round_row: dict, session_state=None) -> dict:
    """Create/update a RoundRecord in the canonical ConversationRecord before provider dispatch."""
    rec = _canonical_record(chat)
    oid = str(round_row.get("round_id") or "").strip()
    if not oid:
        raise ValueError("canonical RoundRecord requires round_id")
    row = dict(round_row)
    row["round_id"] = oid
    existing = next((x for x in rec["rounds"] if isinstance(x, dict) and str(x.get("round_id") or "") == oid), None)
    if existing is None:
        rec["rounds"].append(copy.deepcopy(row))
        existing = rec["rounds"][-1]
    else:
        for k, v in row.items():
            if v not in (None, "", [], {}):
                existing[k] = copy.deepcopy(v)
    commit_canonical_record(chat, session_state)
    return existing


def assert_canonical_lifecycle_ready(chat: dict, message_id: str, request_id: str, round_id: str) -> None:
    """Fail closed unless Message→Request→Round is already canonical and committed."""
    rec = _canonical_record(chat)
    mid, rid, oid = str(message_id or "").strip(), str(request_id or "").strip(), str(round_id or "").strip()
    if not mid or not rid or not oid:
        raise RuntimeError("CANONICAL_LIFECYCLE_NOT_READY: incomplete identity")
    msg = next((x for x in rec["messages"] if isinstance(x, dict) and str(x.get("message_id") or "") == mid), None)
    req = next((x for x in rec["requests"] if isinstance(x, dict) and str(x.get("request_id") or "") == rid), None)
    rnd = next((x for x in rec["rounds"] if isinstance(x, dict) and str(x.get("round_id") or "") == oid), None)
    if not msg or not req or not rnd:
        raise RuntimeError("CANONICAL_LIFECYCLE_NOT_READY: Message/Request/Round missing")
    if str(msg.get("request_id") or "") != rid or str(req.get("message_id") or "") != mid:
        raise RuntimeError("CANONICAL_LIFECYCLE_NOT_READY: Message↔Request mapping mismatch")
    if str(rnd.get("request_id") or "") != rid or str(rnd.get("message_id") or "") != mid:
        raise RuntimeError("CANONICAL_LIFECYCLE_NOT_READY: Request↔Round mapping mismatch")
    if str(msg.get("conversation_id") or "") != str(chat.get("conversation_id") or "") or str(req.get("conversation_id") or "") != str(chat.get("conversation_id") or "") or str(rnd.get("conversation_id") or "") != str(chat.get("conversation_id") or ""):
        raise RuntimeError("CANONICAL_LIFECYCLE_NOT_READY: conversation binding mismatch")

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
    rec = chat.get("conversation_record") if isinstance(chat.get("conversation_record"), dict) else {}
    return {
        "schema": SCHEMA_VERSION,
        "conversation_id": chat.get("conversation_id"),
        "session_id": chat.get("session_id"),
        # Preserve HOTFIX145/V24 snapshot contract.
        "messages": copy.deepcopy(chat.get("message_ledger_v24", [])),
        "rounds": copy.deepcopy(chat.get("round_ledger_v24", [])),
        "requests": copy.deepcopy(chat.get("request_ledger_v24", [])),
        "canonical_conversation_record": {
            "messages": copy.deepcopy(rec.get("messages", [])),
            "requests": copy.deepcopy(rec.get("requests", [])),
            "rounds": copy.deepcopy(rec.get("rounds", [])),
        },
        "bridges": copy.deepcopy(chat.get("bridge_ledger_v24", [])),
        "results": copy.deepcopy(chat.get("result_ledger_v24", [])),
        "provenance": copy.deepcopy(chat.get("provenance_ledger_v24", [])),
        "timeline": copy.deepcopy(chat.get("timeline_ledger_v24", [])),
        "memory": {"L0": copy.deepcopy(chat.get("memory_l0", {})), "L1": copy.deepcopy(chat.get("memory_l1", {})), "L2": copy.deepcopy(chat.get("memory_l2", {})), "L3": copy.deepcopy(chat.get("memory_l3", {}))},
    }
