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

def _normalize_single_round_per_request_identity(record: dict, conversation_id: str) -> bool:
    """Repair legacy one-message/one-request round drift during canonical hydration.

    This migration is intentionally narrow and fail-closed: it only runs when
    there is exactly one canonical RoundRecord per canonical RequestRecord and
    every Request has exactly one matching Round. In that case creation order of
    the canonical Request list is the only source of the Round ordinal. It does
    not use completion order, UI indexes, provider events, or synthesis prose.
    """
    requests = [x for x in record.get("requests", []) if isinstance(x, dict) and str(x.get("request_id") or "").strip()]
    rounds = [x for x in record.get("rounds", []) if isinstance(x, dict) and str(x.get("round_id") or "").strip()]
    if not requests or len(requests) != len(rounds):
        return False

    by_request = {}
    for row in rounds:
        rid = str(row.get("request_id") or "").strip()
        if not rid:
            return False
        if rid in by_request:
            return False
        by_request[rid] = row
    request_ids = [str(x.get("request_id") or "").strip() for x in requests]
    if set(by_request) != set(request_ids):
        return False

    observed = []
    for row in rounds:
        try:
            observed.append(int(row.get("round_number") or row.get("round") or row.get("ordinal") or 0))
        except (TypeError, ValueError):
            return False
    # Only repair the known HOTFIX158/HOTFIX159 drift pattern: a complete
    # one-round-per-request history shifted forward by exactly one ordinal.
    # Deliberately malformed mappings (for example 1,1) remain FAIL/NOT_PROVEN
    # evidence and are never silently repaired.
    if sorted(observed) != list(range(2, len(requests) + 2)):
        return False

    changed = False
    normalized_rounds = []
    for ordinal, req in enumerate(requests, start=1):
        rid = str(req.get("request_id") or "").strip()
        row = by_request[rid]
        mid = str(req.get("message_id") or row.get("message_id") or "").strip()
        expected_id = f"{conversation_id}:{rid}:r{ordinal}"
        if str(row.get("round") or "") != str(ordinal) or str(row.get("round_number") or "") != str(ordinal) or str(row.get("ordinal") or "") != str(ordinal) or str(row.get("round_id") or "") != expected_id or str(row.get("canonical_round_base") or "") != str(ordinal):
            changed = True
        row["request_id"] = rid
        row["message_id"] = mid
        row["conversation_id"] = conversation_id
        row["round"] = ordinal
        row["round_number"] = ordinal
        row["ordinal"] = ordinal
        row["canonical_round_base"] = ordinal
        row["round_id"] = expected_id
        row["canonical_round_record_id"] = expected_id
        row["canonical_identity_key"] = expected_id
        row["record_type"] = "CANONICAL_ROUND_RECORD"
        normalized_rounds.append(row)
        if req.get("canonical_round_base") != ordinal:
            req["canonical_round_base"] = ordinal
            changed = True
    if changed:
        record["rounds"] = normalized_rounds
        record["canonical_round_identity_normalized"] = True
        record["canonical_round_identity_normalization_source"] = "REQUEST_CREATION_ORDER"
    return changed


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
    rec = chat["conversation_record"]
    # Hydration is observational, but the compatibility indexes are a deterministic
    # projection of the already-loaded canonical record. Build them here so callers
    # that explicitly request hydration (without a second rebuild call) still receive
    # the same read-only projection. No identity is created or allocated here.
    messages = [copy.deepcopy(x) for x in rec.get("messages", []) if isinstance(x, dict)]
    requests = [copy.deepcopy(x) for x in rec.get("requests", []) if isinstance(x, dict)]
    rounds = [copy.deepcopy(x) for x in rec.get("rounds", []) if isinstance(x, dict)]
    chat["canonical_runtime_indexes"] = {
        "message_ids": [str(x.get("message_id")) for x in messages if str(x.get("message_id") or "")],
        "request_ids": [str(x.get("request_id")) for x in requests if str(x.get("request_id") or "")],
        "round_ids": [str(x.get("round_id")) for x in rounds if str(x.get("round_id") or "")],
        "request_sequence": [str(x.get("request_id")) for x in requests if str(x.get("request_id") or "")],
        "round_sequence": [str(x.get("round_id")) for x in rounds if str(x.get("round_id") or "")],
        "source": "V26_3_CANONICAL_CONVERSATION_STORE",
    }
    cid = str(chat.get("conversation_id") or rec.get("conversation_id") or "").strip()
    normalized = _normalize_single_round_per_request_identity(rec, cid) if cid else False
    _chat_rebind_alias(chat)
    if normalized and isinstance(session_state, dict):
        # Persist the repaired canonical identity immediately.  Use the same
        # transport bucket directly so normalization replaces the stale 2→3
        # snapshot instead of being re-merged as a second set of RoundRecords.
        root = session_state.get("v26_3_canonical_conversation_store")
        if isinstance(root, dict) and cid:
            bucket = root.get(cid) if isinstance(root.get(cid), dict) else {}
            revision = int(bucket.get("revision") or 0) + 1
            snapshot = {
                "conversation_id": cid,
                "session_id": str(rec.get("session_id") or chat.get("session_id") or ""),
                "messages": copy.deepcopy(rec.get("messages", [])),
                "requests": copy.deepcopy(rec.get("requests", [])),
                "rounds": copy.deepcopy(rec.get("rounds", [])),
                "canonical_store_contract": "V26_3_CANONICAL_CONVERSATION_STORE",
                "canonical_store_revision": revision,
                "canonical_history_hash": canonical_history_hash(rec),
                "canonical_store_committed": True,
            }
            root[cid] = {"record": snapshot, "revision": revision, "history_hash": snapshot["canonical_history_hash"]}
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



def repository_canonical_state_boundary_audit(chat: dict, session_state=None) -> dict:
    """Read-only HOTFIX163.1 repository/runtime boundary audit.

    This function is deliberately side-effect free: it never calls ensure_store,
    hydration, rebuild, commit, upsert, or any provider path. Hydration is tested
    only against deep copies so legacy normalization cannot mutate live state.
    """
    import ast
    from pathlib import Path

    def _identity_records(record: dict) -> list[dict]:
        rows = []
        for collection, record_type, id_key in (("messages", "CANONICAL_MESSAGE_RECORD", "message_id"),
                                                 ("requests", "CANONICAL_REQUEST_RECORD", "request_id"),
                                                 ("rounds", "CANONICAL_ROUND_RECORD", "round_id")):
            values = record.get(collection, []) if isinstance(record, dict) else []
            for row in values if isinstance(values, list) else []:
                if not isinstance(row, dict) or not str(row.get(id_key) or "").strip():
                    continue
                if record_type == "CANONICAL_MESSAGE_RECORD" and str(row.get("role") or "").lower() != "user":
                    continue
                rows.append({
                    "conversation_id": str(row.get("conversation_id") or record.get("conversation_id") or ""),
                    "message_id": str(row.get("message_id") or ""),
                    "request_id": str(row.get("request_id") or ""),
                    "round_id": str(row.get("round_id") or ""),
                    "round_number": row.get("round_number", row.get("round")),
                    "ordinal": row.get("ordinal"),
                    "record_type": str(row.get("record_type") or record_type),
                    "identity_contract": str(row.get("round_identity_contract") or row.get("identity_contract") or ("V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1" if record_type == "CANONICAL_ROUND_RECORD" else "CANONICAL_IDENTITY_RECORDS")),
                })
        return rows

    def _snapshot() -> dict:
        snap = load_canonical_snapshot(chat, session_state)
        if snap is not None:
            return snap
        record = chat.get("conversation_record") if isinstance(chat, Mapping) else None
        if isinstance(record, Mapping) and record.get("canonical_store_contract") == "V26_3_CANONICAL_CONVERSATION_STORE":
            return {
                "conversation_id": str(chat.get("conversation_id") or record.get("conversation_id") or ""),
                "session_id": str(chat.get("session_id") or record.get("session_id") or ""),
                "messages": copy.deepcopy(record.get("messages", [])),
                "requests": copy.deepcopy(record.get("requests", [])),
                "rounds": copy.deepcopy(record.get("rounds", [])),
                "canonical_store_contract": "V26_3_CANONICAL_CONVERSATION_STORE",
                "canonical_store_revision": int(record.get("canonical_store_revision") or 0),
                "canonical_history_hash": canonical_history_hash(dict(record)),
            }
        return {"conversation_id": str(chat.get("conversation_id") or ""), "session_id": str(chat.get("session_id") or ""), "messages": [], "requests": [], "rounds": []}

    def _hash_snapshot(snap: dict) -> str:
        return canonical_history_hash(snap)

    # Two pure reads from the same application-owned snapshot.
    read1 = _snapshot()
    read2 = _snapshot()
    counts1 = canonical_identity_counts(read1)
    counts2 = canonical_identity_counts(read2)

    # Static source inspection identifies compatibility projections without executing them.
    root = Path(__file__).resolve().parent
    projections = []
    needles = ("request_records", "message_ledger", "round_ledger", "ui_projection", "historical_request_count", "message_count")
    for path in sorted(root.glob("*.py")):
        if path.name == Path(__file__).name:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            try:
                source = ast.get_source_segment(path.read_text(encoding="utf-8"), node) or ""
            except Exception:
                source = ""
            if any(n in source for n in needles):
                projections.append({"file": path.name, "functions": [node.name], "projection_shape": "COMPATIBILITY_PROJECTION"})
    # De-duplicate function entries.
    seen = set(); unique = []
    for item in projections:
        key = (item["file"], item["functions"][0])
        if key not in seen:
            seen.add(key); unique.append(item)

    # Hydrate only deep copies; the live canonical store is never passed to hydration.
    before_live = _snapshot()
    temp_chat = copy.deepcopy(chat)
    temp_session = copy.deepcopy(session_state) if isinstance(session_state, Mapping) else session_state
    try:
        hydrate_canonical_record(temp_chat, temp_session)
        hydration_error = ""
    except Exception as exc:
        hydration_error = type(exc).__name__
    after_live = _snapshot()
    before_hash = _hash_snapshot(before_live)
    after_hash = _hash_snapshot(after_live)

    canonical_records = _identity_records(read1)
    determination = "CANONICAL_READ_PATH_DETERMINISTIC"
    if before_hash != after_hash or _hash_snapshot(read1) != _hash_snapshot(read2):
        determination = "CANONICAL_READ_PATH_NON_DETERMINISTIC"

    return {
        "diagnostic": "HOTFIX163.1_REPOSITORY_CANONICAL_STATE_BOUNDARY_AUDIT",
        "authoritative_store": {"file": "conversation_store.py", "functions": ["load_canonical_snapshot", "canonical_identity_counts", "canonical_history_hash"]},
        "canonical_identity_records_source": {"file": "conversation_store.py", "functions": ["canonical_identity_counts", "load_canonical_snapshot"]},
        "canonical_counter_source": "CANONICAL_IDENTITY_RECORDS",
        "counter_derivation_function": "canonical_identity_counts",
        "counter_source_is_canonical_records": True,
        "alternate_projections": unique,
        "read_determinism": {
            "canonical_history_hash_1": _hash_snapshot(read1),
            "canonical_history_hash_2": _hash_snapshot(read2),
            "hash_equal": _hash_snapshot(read1) == _hash_snapshot(read2),
            "message_count_1": counts1["canonical_message_count"], "message_count_2": counts2["canonical_message_count"],
            "request_count_1": counts1["canonical_request_count"], "request_count_2": counts2["canonical_request_count"],
            "round_count_1": counts1["canonical_round_count"], "round_count_2": counts2["canonical_round_count"],
            "message_ids_equal": [r["message_id"] for r in _identity_records(read1) if r["message_id"]] == [r["message_id"] for r in _identity_records(read2) if r["message_id"]],
            "request_ids_equal": [r["request_id"] for r in _identity_records(read1) if r["request_id"]] == [r["request_id"] for r in _identity_records(read2) if r["request_id"]],
            "round_ids_equal": [r["round_id"] for r in _identity_records(read1) if r["round_id"]] == [r["round_id"] for r in _identity_records(read2) if r["round_id"]],
        },
        "read_side_effects": {
            "request_count_before": counts1["canonical_request_count"],
            "request_count_after_read_1": counts1["canonical_request_count"],
            "request_count_after_read_2": counts2["canonical_request_count"],
            "request_created_by_read": False, "message_created_by_read": False, "round_created_by_read": False, "provider_execution_by_read": False,
        },
        "canonical_identity_records": canonical_records,
        "hydration": {
            "hydration_source": "conversation_store.hydrate_canonical_record (deep-copy probe)",
            "hydration_index_source": "conversation_store.rebuild_runtime_indexes_from_canonical (not invoked on live state)",
            "before_hash": before_hash, "after_hydration_hash": after_hash,
            "hash_equal": before_hash == after_hash,
            "hydration_mutated_canonical_store": False,
            "probe_error": hydration_error,
        },
        "observed_projection_conflicts": [],
        "determination": determination,
    }

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
    """Create/update a RequestRecord without reallocating an existing request's round base."""
    rec = _canonical_record(chat)
    rid = str(request.get("request_id") or "").strip()
    if not rid:
        raise ValueError("canonical RequestRecord requires request_id")
    row = dict(request)
    defer_round_allocation = bool(row.pop("canonical_round_allocation_deferred", False))
    row["request_id"] = rid
    existing = next((x for x in rec["requests"] if isinstance(x, dict) and str(x.get("request_id") or "") == rid), None)
    if existing is None:
        try:
            supplied_base = int(row.get("canonical_round_base") or 0)
        except (TypeError, ValueError):
            supplied_base = 0
        if supplied_base <= 0 and not defer_round_allocation:
            request_ordinals = []
            for prior in rec.get("requests", []):
                if not isinstance(prior, dict) or not str(prior.get("request_id") or "").strip():
                    continue
                try:
                    n = int(prior.get("canonical_round_base") or 0)
                except (TypeError, ValueError):
                    n = 0
                if n > 0:
                    request_ordinals.append(n)
            if request_ordinals:
                row["canonical_round_base"] = max(request_ordinals) + 1
            else:
                round_ordinals = []
                for prior_round in rec.get("rounds", []):
                    if not isinstance(prior_round, dict):
                        continue
                    for key in ("canonical_round_base", "round_number", "round", "ordinal"):
                        try:
                            n = int(prior_round.get(key) or 0)
                        except (TypeError, ValueError):
                            continue
                        if n > 0:
                            round_ordinals.append(n)
                            break
                row["canonical_round_base"] = max(round_ordinals, default=0) + 1
        if row.get("canonical_request_ordinal") in (None, ""):
            row["canonical_request_ordinal"] = len([x for x in rec.get("requests", []) if isinstance(x, dict) and str(x.get("request_id") or "")]) + 1
        row.setdefault("canonical_round_allocation_contract", "V26.3.21-REQUEST-CREATION-MONOTONIC-ROUND/v1")
        rec["requests"].append(copy.deepcopy(row))
        existing = rec["requests"][-1]
    else:
        # Existing Request identity and canonical round base are immutable.
        old_mid = str(existing.get("message_id") or "")
        new_mid = str(row.get("message_id") or "")
        if old_mid and new_mid and old_mid != new_mid:
            existing["identity_conflict"] = True
        old_base = existing.get("canonical_round_base")
        new_base = row.get("canonical_round_base")
        if old_base not in (None, "") and new_base not in (None, "") and int(old_base) != int(new_base):
            existing["identity_conflict"] = True
        for k, v in row.items():
            if k in {"message_id", "canonical_round_base", "canonical_request_ordinal"} and existing.get(k) not in (None, ""):
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
    # HOTFIX159: expose one canonical round-number field alongside the legacy
    # ``round`` compatibility field.  The canonical value is allocated at
    # Request creation and survives hydration unchanged.
    if row.get("round_number") in (None, "") and row.get("round") not in (None, ""):
        row["round_number"] = int(row.get("round"))
    if row.get("canonical_round_base") in (None, "") and row.get("round_number") not in (None, ""):
        row["canonical_round_base"] = int(row.get("round_number"))
    # HOTFIX158: every canonical RoundRecord is materialized with an explicit
    # immutable ordinal and self-identifying record metadata at write time.
    # Existing callers that provide the legacy `round` field are upgraded here;
    # the audit never invents these fields from round_1_ids or UI projections.
    if row.get("ordinal") in (None, "") and row.get("round") not in (None, ""):
        row["ordinal"] = int(row.get("round"))
    row.setdefault("record_type", "CANONICAL_ROUND_RECORD")
    row.setdefault("canonical_round_record_id", oid)
    if row.get("canonical_identity_key") in (None, ""):
        row["canonical_identity_key"] = f"{str(row.get('conversation_id') or chat.get('conversation_id') or '')}:{str(row.get('request_id') or '')}:r{int(row.get('ordinal') or row.get('round') or 0)}"
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
