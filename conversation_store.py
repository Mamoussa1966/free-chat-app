from __future__ import annotations
import copy
import hashlib
import json
from collections.abc import Mapping
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
    rec.setdefault("canonical_store_contract", "V26_3_CANONICAL_CONVERSATION_STORE")
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

def canonical_history_hash(record: dict) -> str:
    """Deterministic identity hash over canonical Message/Request/Round history."""
    payload = {
        "conversation_id": str(record.get("conversation_id") or ""),
        "session_id": str(record.get("session_id") or ""),
        "messages": [
            {k: x.get(k) for k in ("message_id", "conversation_id", "session_id", "role", "request_id", "created_at")}
            for x in record.get("messages", []) if isinstance(x, dict) and x.get("message_id")
        ],
        "requests": [
            {k: x.get(k) for k in ("request_id", "conversation_id", "session_id", "message_id", "created_at", "state")}
            for x in record.get("requests", []) if isinstance(x, dict) and x.get("request_id")
        ],
        "rounds": [
            {k: x.get(k) for k in ("round_id", "conversation_id", "session_id", "message_id", "request_id", "round", "round_identity_contract", "created_at", "status")}
            for x in record.get("rounds", []) if isinstance(x, dict) and x.get("round_id")
        ],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def validate_canonical_chain(record: dict) -> dict:
    """Validate the immutable Message→Request→Round graph without inference."""
    messages = [x for x in record.get("messages", []) if isinstance(x, dict)]
    requests = [x for x in record.get("requests", []) if isinstance(x, dict)]
    rounds = [x for x in record.get("rounds", []) if isinstance(x, dict)]
    mids = {str(x.get("message_id") or "") for x in messages if x.get("message_id")}
    rids = {str(x.get("request_id") or "") for x in requests if x.get("request_id")}
    oids = [str(x.get("round_id") or "") for x in rounds if x.get("round_id")]
    msg_req = all(str(x.get("request_id") or "") in rids for x in messages if str(x.get("role") or "").lower() == "user")
    req_msg = all(str(x.get("message_id") or "") in mids for x in requests if x.get("message_id"))
    round_req = all(str(x.get("request_id") or "") in rids and str(x.get("message_id") or "") in mids for x in rounds if x.get("round_id"))
    return {
        "message_request_integrity": bool(msg_req and req_msg),
        "request_round_integrity": bool(round_req),
        "round_ids_unique": len(oids) == len(set(oids)),
        "history_hash": canonical_history_hash(record),
    }

def canonical_create_lifecycle(chat: dict, message: dict, request: dict, round_row: dict, session_state=None) -> dict:
    """Atomically append Message/Request/Round identity and commit one canonical snapshot."""
    rec = _canonical_record(chat)
    snapshot = copy.deepcopy(rec)
    try:
        canonical_upsert_message(chat, message, None)
        canonical_upsert_request(chat, request, None)
        canonical_upsert_round(chat, round_row, None)
        integrity = validate_canonical_chain(_canonical_record(chat))
        if not all(integrity.values()):
            raise RuntimeError("CANONICAL_ATOMIC_LIFECYCLE_VALIDATION_FAILED")
        commit_canonical_record(chat, session_state)
        return {"committed": True, "integrity": integrity, "record": copy.deepcopy(_canonical_record(chat))}
    except Exception:
        chat["conversation_record"] = snapshot
        _chat_rebind_alias(chat)
        raise

def _restore_saved_identity_order(target: list, saved: list, identity_key: str) -> list:
    """Restore canonical historical order from the committed snapshot.

    Streamlit reruns may leave a narrowed current list (for example Request 2)
    while the committed snapshot still contains [Request 1, Request 2].  The
    committed snapshot is the authoritative sequence; never let the narrowed
    runtime list determine historical ordering. Existing identity rows are
    merged by immutable ID, then emitted in saved canonical order followed by
    genuinely new rows.
    """
    current_by_id = {str(x.get(identity_key) or ""): x for x in target if isinstance(x, dict) and str(x.get(identity_key) or "")}
    ordered = []
    seen = set()
    for item in saved if isinstance(saved, list) else []:
        if not isinstance(item, dict):
            continue
        ident = str(item.get(identity_key) or "")
        if not ident or ident in seen:
            continue
        row = current_by_id.pop(ident, None)
        if row is None:
            row = copy.deepcopy(item)
        else:
            for k, v in item.items():
                if v not in (None, "", [], {}):
                    row[k] = copy.deepcopy(v)
        ordered.append(row)
        seen.add(ident)
    # Preserve any current-only records after the committed historical prefix.
    ordered.extend(current_by_id.values())
    return ordered


def commit_canonical_record(chat: dict, session_state=None) -> dict:
    """Commit the complete canonical ConversationRecord at a lifecycle boundary.

    The chat ConversationRecord remains authoritative. Session State is only the
    transport backing used to survive Streamlit script reruns; it is a deep-copy
    checkpoint of the complete record, never a current-request audit source.
    """
    rec = _canonical_record(chat)
    rec["canonical_store_contract"] = "V26_3_CANONICAL_CONVERSATION_STORE"
    cid = str(chat.get("conversation_id") or "").strip()
    if not cid:
        return rec
    touch(chat)
    # The in-memory ConversationRecord is itself the application-owned canonical
    # ledger. SessionState is only the rerun transport checkpoint. Mark the record
    # committed even when no transport mapping is supplied so tests/runtime paths
    # can audit the ledger directly without inventing a second source of truth.
    rec["canonical_store_committed"] = True
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
                incoming = saved.get(key, []) if isinstance(saved.get(key), list) else []
                rec[key] = _restore_saved_identity_order(target, incoming, ident)
            _chat_rebind_alias(chat)
        # HOTFIX118: build the complete candidate snapshot first, validate it,
        # then replace the transport bucket in one assignment. This prevents a
        # partially-mutated current chat from becoming the canonical snapshot.
        rec["canonical_store_contract"] = "V26_3_CANONICAL_CONVERSATION_STORE"
        rec["canonical_store_committed"] = True
        candidate = copy.deepcopy({
            "conversation_id": cid,
            "session_id": str(chat.get("session_id") or ""),
            "messages": rec.get("messages", []),
            "requests": rec.get("requests", []),
            "rounds": rec.get("rounds", []),
            "canonical_store_contract": "V26_3_CANONICAL_CONVERSATION_STORE",
            "canonical_store_committed": True,
        })
        # A normal lifecycle commits partial identity checkpoints (Request before
        # Round creation, then Round start/finish). Full graph validation belongs
        # to canonical_create_lifecycle/assert_canonical_lifecycle_ready; COMMIT
        # itself must therefore accept a valid partial lifecycle while still
        # enforcing unique immutable Round IDs.
        candidate_integrity = validate_canonical_chain(candidate)
        if not candidate_integrity.get("round_ids_unique"):
            raise RuntimeError("CANONICAL_ATOMIC_COMMIT_ROUND_ID_COLLISION")
        previous = root.get(cid) if isinstance(root.get(cid), dict) else {}
        revision = int(previous.get("revision") or 0) + 1
        root[cid] = copy.deepcopy({
            "schema": "v26.3.20-v26_3-canonical-conversation-store/v12",
            "contract": "V26_3_CANONICAL_CONVERSATION_STORE",
            "conversation_id": cid,
            "session_id": str(chat.get("session_id") or ""),
            "revision": revision,
            "history_hash": candidate_integrity.get("history_hash"),
            "record": candidate,
        })
        # Compatibility projection into the exact same canonical bucket.
        root[cid]["messages"] = root[cid]["record"]["messages"]
        root[cid]["requests"] = root[cid]["record"]["requests"]
        root[cid]["rounds"] = root[cid]["record"]["rounds"]
        rec["canonical_store_committed"] = True
        rec["canonical_store_revision"] = revision
    return rec

def load_canonical_snapshot(chat: dict, session_state=None) -> dict | None:
    """Read the ONE V26_3_CANONICAL_CONVERSATION_STORE snapshot.

    The writer and reader share one contract.  Session State is only the
    rerun transport for that same store; the embedded ConversationRecord is
    the durable application-owned representation.  No legacy/current-request
    fallback is permitted.
    """
    cid = str(chat.get("conversation_id") or "").strip()
    if not cid:
        return None

    # Streamlit session_state is Mapping-like, not necessarily a dict.
    if isinstance(session_state, Mapping):
        root = session_state.get("v26_3_canonical_conversation_store")
        if isinstance(root, Mapping):
            bucket = root.get(cid)
            if isinstance(bucket, Mapping) and isinstance(bucket.get("record"), Mapping):
                rec = bucket["record"]
                return {
                    "conversation_id": cid,
                    "session_id": str(rec.get("session_id") or chat.get("session_id") or ""),
                    "messages": copy.deepcopy(rec.get("messages", [])),
                    "requests": copy.deepcopy(rec.get("requests", [])),
                    "rounds": copy.deepcopy(rec.get("rounds", [])),
                    "canonical_store_contract": "V26_3_CANONICAL_CONVERSATION_STORE",
                    "canonical_store_revision": int(bucket.get("revision") or 0),
                    "canonical_history_hash": str(bucket.get("history_hash") or ""),
                }

    # Same canonical record, not a second persistence source.  This path is
    # required when Streamlit restores the conversation object but its mapping
    # transport is not exposed as a plain dict.
    record = chat.get("conversation_record") if isinstance(chat, Mapping) else None
    if isinstance(record, Mapping) and record.get("canonical_store_committed") is True:
        if record.get("canonical_store_contract") == "V26_3_CANONICAL_CONVERSATION_STORE":
            return {
                "conversation_id": cid,
                "session_id": str(record.get("session_id") or chat.get("session_id") or ""),
                "messages": copy.deepcopy(record.get("messages", [])),
                "requests": copy.deepcopy(record.get("requests", [])),
                "rounds": copy.deepcopy(record.get("rounds", [])),
                "canonical_store_contract": "V26_3_CANONICAL_CONVERSATION_STORE",
                "canonical_store_revision": int(record.get("canonical_store_revision") or 0),
                "canonical_history_hash": canonical_history_hash(dict(record)),
            }
    return None


def prepare_historical_runtime(chat: dict, session_state=None) -> dict:
    """Start a new lifecycle from the last committed canonical snapshot.

    The critical invariant is: Message N+1 is allocated only after Message N's
    committed Message/Request/Round graph has been restored.  A narrowed current
    runtime can therefore never become the base for the next canonical commit.
    """
    snapshot = load_canonical_snapshot(chat, session_state)
    if snapshot is not None:
        chat["conversation_record"] = snapshot
        _chat_rebind_alias(chat)
        rebuild_runtime_indexes_from_canonical(chat, session_state)
        return snapshot
    return _canonical_record(chat)

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
    # HOTFIX116: HYDRATE is authoritative transport restoration.  A Streamlit
    # rerun may leave chat["conversation_record"] narrowed to Message 2 /
    # Request 2.  Merging that narrow object into the saved object is unsafe
    # because later lifecycle code can accidentally audit the narrow view.
    # The canonical session transport has already been committed monotonically,
    # so restore the complete immutable-identity record first.
    current = chat["conversation_record"]
    if isinstance(saved_record, dict) and any(isinstance(saved_record.get(k), list) and saved_record.get(k) for k in ("messages", "requests", "rounds")):
        chat["conversation_record"] = copy.deepcopy(saved_record)
    else:
        chat["conversation_record"] = current
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
    """Rebuild all compatibility/runtime indexes strictly from canonical history."""
    hydrate_canonical_record(chat, session_state)
    rec = _canonical_record(chat)
    messages = [copy.deepcopy(x) for x in rec.get("messages", []) if isinstance(x, dict)]
    requests = [copy.deepcopy(x) for x in rec.get("requests", []) if isinstance(x, dict)]
    rounds = [copy.deepcopy(x) for x in rec.get("rounds", []) if isinstance(x, dict)]
    chat["message_ledger"] = messages[-1000:]
    chat["request_records"] = requests[-1000:]
    chat["round_ledger"] = rounds[-2000:]
    # Explicitly expose the rebuilt canonical runtime indexes so V26.3.9/V26.3.13
    # can prove hydration rebuilt the runtime projection rather than merely loaded
    # a blob. These are compatibility indexes, never a second source of truth.
    chat["canonical_runtime_indexes"] = {
        "message_ids": [str(x.get("message_id")) for x in messages if str(x.get("message_id") or "")],
        "request_ids": [str(x.get("request_id")) for x in requests if str(x.get("request_id") or "")],
        "round_ids": [str(x.get("round_id")) for x in rounds if str(x.get("round_id") or "")],
        "request_sequence": [str(x.get("request_id")) for x in requests if str(x.get("request_id") or "")],
        "round_sequence": [str(x.get("round_id")) for x in rounds if str(x.get("round_id") or "")],
        "source": "V26_3_CANONICAL_CONVERSATION_STORE",
    }
    return chat


def canonical_identity_counts(record: dict) -> dict:
    """Return canonical Message/Request/Round counts from one identity record set.

    Contract: canonical messages are identity-bearing USER MessageRecords only;
    canonical requests require request_id; canonical rounds require round_id.
    UI/projection lists are never consulted.
    """
    if not isinstance(record, dict):
        return {
            "canonical_message_count": "NOT_PROVEN",
            "canonical_request_count": "NOT_PROVEN",
            "canonical_round_count": "NOT_PROVEN",
        }
    messages = record.get("messages") if isinstance(record.get("messages"), list) else []
    requests = record.get("requests") if isinstance(record.get("requests"), list) else []
    rounds = record.get("rounds") if isinstance(record.get("rounds"), list) else []
    return {
        "canonical_message_count": len([x for x in messages if isinstance(x, dict) and str(x.get("message_id") or "").strip() and str(x.get("role") or "").lower() == "user"]),
        "canonical_request_count": len([x for x in requests if isinstance(x, dict) and str(x.get("request_id") or "").strip()]),
        "canonical_round_count": len([x for x in rounds if isinstance(x, dict) and str(x.get("round_id") or "").strip()]),
    }


def canonical_audit_preflight(chat: dict, session_state=None) -> dict:
    """Canonical Audit Preflight: the mandatory application-owned audit gate.

    HOTFIX154 contract: every persistence/audit path that claims canonical
    authority must invoke this function. Invocation is observable outside the
    canonical identity record, while all counters still come exclusively from
    canonical Message/Request/Round identity records.
    """
    ensure_store(chat)
    marker = chat.get("canonical_audit_preflight_runtime")
    if not isinstance(marker, dict):
        marker = {}
    marker["invocation_count"] = int(marker.get("invocation_count") or 0) + 1
    marker["last_invocation_source"] = "APPLICATION_OWNED_AUDIT_GATE"
    chat["canonical_audit_preflight_runtime"] = marker
    snapshot = load_canonical_snapshot(chat, session_state)
    # Structural/audit callers may already hold the same canonical record in
    # the conversation object without a Session-State transport bucket. Reuse
    # that single record; never fall back to UI/current-request projections.
    if snapshot is None:
        rec0 = chat.get("conversation_record") if isinstance(chat.get("conversation_record"), dict) else None
        if isinstance(rec0, dict) and rec0.get("canonical_store_contract") == "V26_3_CANONICAL_CONVERSATION_STORE" and all(isinstance(rec0.get(k), list) for k in ("messages", "requests", "rounds")):
            snapshot = {
                "conversation_id": str(chat.get("conversation_id") or rec0.get("conversation_id") or ""),
                "session_id": str(chat.get("session_id") or rec0.get("session_id") or ""),
                "messages": copy.deepcopy(rec0.get("messages", [])),
                "requests": copy.deepcopy(rec0.get("requests", [])),
                "rounds": copy.deepcopy(rec0.get("rounds", [])),
                "canonical_store_contract": "V26_3_CANONICAL_CONVERSATION_STORE",
                "canonical_store_revision": int(rec0.get("canonical_store_revision") or 0),
                "canonical_history_hash": canonical_history_hash(rec0),
            }
    if snapshot is None:
        return {
            "status": "NOT_PROVEN",
            "source": "V26_3_CANONICAL_CONVERSATION_STORE",
            "canonical_store_loaded": False,
            "canonical_message_count": "NOT_PROVEN",
            "canonical_request_count": "NOT_PROVEN",
            "canonical_round_count": "NOT_PROVEN",
            "canonical_runtime_indexes_rebuilt": False,
            "identity_chain_valid": False,
        }
    # Audit/preflight is observational. Preserve existing runtime/UI projection
    # fields because rebuilding compatibility indexes must never erase the
    # current request execution record while merely proving canonical history.
    projection_backup = {
        key: copy.deepcopy(chat.get(key))
        for key in ("messages", "request_records", "message_ledger", "round_ledger", "canonical_runtime_indexes")
        if key in chat
    }
    hydrate_canonical_record(chat, session_state)
    rebuild_runtime_indexes_from_canonical(chat, session_state)
    rec = _canonical_record(chat)
    integrity = validate_canonical_chain(rec)
    counts = canonical_identity_counts(rec)
    indexes = chat.get("canonical_runtime_indexes") if isinstance(chat.get("canonical_runtime_indexes"), dict) else {}
    index_ok = all(isinstance(indexes.get(k), list) for k in ("message_ids", "request_ids", "round_ids"))
    chain_ok = bool(integrity.get("message_request_integrity") and integrity.get("request_round_integrity") and integrity.get("round_ids_unique"))
    count_values = [counts[k] for k in ("canonical_message_count", "canonical_request_count", "canonical_round_count")]
    identity_counts_valid = all(isinstance(v, int) and v >= 0 for v in count_values)
    evidence_present = bool(identity_counts_valid and sum(count_values) > 0)
    counter_semantics_consistent = bool(evidence_present and all(
        isinstance(x, dict) for x in rec.get("messages", []) if isinstance(rec.get("messages"), list)
    ))
    result = {
        "status": "PASS" if index_ok and chain_ok and evidence_present else "NOT_PROVEN" if not evidence_present else "FAIL",
        "source": "V26_3_CANONICAL_CONVERSATION_STORE",
        "canonical_store_loaded": True,
        **counts,
        "canonical_runtime_indexes_rebuilt": index_ok,
        "identity_chain_valid": chain_ok,
        "canonical_counter_source": "CANONICAL_IDENTITY_RECORDS",
        "counter_semantics_consistent": counter_semantics_consistent,
        "ui_projection_consulted": False,
        "history_hash": integrity.get("history_hash"),
        "request_sequence": indexes.get("request_sequence", []),
        "round_sequence": indexes.get("round_sequence", []),
    }
    for key, value in projection_backup.items():
        chat[key] = value
    return result


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
        old_req = str(existing.get("request_id") or "")
        new_req = str(row.get("request_id") or "")
        if old_req and new_req and old_req != new_req:
            existing["identity_conflict"] = True
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
    # Request creation owns the immutable conversation round allocation.
    # Callers may provide the value (the production orchestrator does), but
    # direct canonical writers receive the same deterministic contract.
    if row.get("canonical_round_base") in (None, ""):
        bases = []
        for existing_round in rec.get("rounds", []):
            try:
                n = int(existing_round.get("round") or 0)
            except (TypeError, ValueError):
                n = 0
            if n > 0:
                bases.append(n)
        row["canonical_round_base"] = max(bases, default=0)
    if row.get("canonical_request_ordinal") in (None, ""):
        row["canonical_request_ordinal"] = len([x for x in rec.get("requests", []) if isinstance(x, dict) and str(x.get("request_id") or "")]) + 1
    existing = next((x for x in rec["requests"] if isinstance(x, dict) and str(x.get("request_id") or "") == rid), None)
    if existing is None:
        rec["requests"].append(copy.deepcopy(row))
        existing = rec["requests"][-1]
    else:
        old_mid = str(existing.get("message_id") or "")
        new_mid = str(row.get("message_id") or "")
        if old_mid and new_mid and old_mid != new_mid:
            existing["identity_conflict"] = True
        for k, v in row.items():
            if k == "message_id" and old_mid and new_mid and old_mid != new_mid:
                continue
            if k == "canonical_round_base" and existing.get(k) not in (None, "") and v not in (None, "") and int(existing.get(k)) != int(v):
                existing["identity_conflict"] = True
                continue
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
        for identity_key in ("request_id", "message_id", "conversation_id", "session_id", "round"):
            old_value = str(existing.get(identity_key) or "")
            new_value = str(row.get(identity_key) or "")
            if old_value and new_value and old_value != new_value:
                existing["identity_conflict"] = True
        for k, v in row.items():
            if k in {"request_id", "message_id", "conversation_id", "session_id", "round"} and existing.get(k) not in (None, "") and v not in (None, "") and str(existing.get(k)) != str(v):
                continue
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
