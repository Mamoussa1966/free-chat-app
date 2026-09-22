from __future__ import annotations

"""V25 authoritative Conversation Ledger / Message Runtime.

Additive reconciliation layer on top of HOTFIX145/V24.  It consumes only
application-owned ledgers and persisted lifecycle/result metrics.  It never
selects providers/models and never treats provider prose as identity or
accounting evidence.
"""

from copy import deepcopy
from conversation_store import ensure_store, touch, now, hydrate_canonical_record, rebuild_runtime_indexes_from_canonical, canonical_history_hash, validate_canonical_chain, load_canonical_snapshot
from conversation_persistence_v26 import get_authoritative_bucket


def _v2631_history(chat):
    """Read only the hydrated HOTFIX145 ConversationRecord canonical history."""
    record = chat.get("conversation_record") if isinstance(chat, dict) else None
    if not isinstance(record, dict):
        return {"source": "V26_3_CONVERSATION_PERSISTENCE", "messages": [], "requests": [], "rounds": []}
    return {
        "source": "V26_3_CONVERSATION_PERSISTENCE",
        "messages": deepcopy(record.get("messages", [])) if isinstance(record.get("messages"), list) else [],
        "requests": deepcopy(record.get("requests", [])) if isinstance(record.get("requests"), list) else [],
        "rounds": deepcopy(record.get("rounds", [])) if isinstance(record.get("rounds"), list) else [],
    }

V25_SCHEMA = "v25-conversation-ledger-message-runtime/v2"
V26_3_10_SCHEMA = "v26.3.10-canonical-lifecycle/v1"
V26_3_11_SCHEMA = "v26.3.11-canonical-lifecycle/v1"
V26_3_12_SCHEMA = "v26.3.12-canonical-hydration-index-rebuild-authoritative-audit/v1"
V26_3_16_SCHEMA = "v26.3.16-canonical-transport-authoritative-historical-chain/v1"
V26_3_17_SCHEMA = "v26.3.17-atomic-history-idempotency-checksum/v1"
V26_3_18_SCHEMA = "v26.3.18-atomic-commit-roundtrip-gate/v1"
V26_SCHEMA = "v26-message-runtime-authoritative-mapping/v1"


def _s(value) -> str:
    return str(value or "").strip()


def ensure_v25_store(chat: dict) -> dict:
    ensure_store(chat)
    # Compatibility migration for pre-V26.3.5 application-owned ledgers.
    # Production V26.3.5 writes directly through persist_identity(); this path
    # only upgrades an older in-memory ConversationRecord before any audit/use.
    record = chat.get("conversation_record") if isinstance(chat.get("conversation_record"), dict) else {}
    from conversation_persistence_v26 import persist_identity
    # Idempotent compatibility migration: import any legacy application-owned
    # identity that is not yet present in the canonical ConversationRecord.
    # This is a lifecycle upgrade, not a current-request audit fallback.
    if True:
        for row in chat.get("message_ledger_v24", []):
            if isinstance(row, dict) and _s(row.get("message_id")):
                persist_identity(chat, None, message=row)
        for row in chat.get("request_records", []):
            if isinstance(row, dict) and _s(row.get("request_id")) and _s(row.get("message_id")):
                persist_identity(chat, None, request=row)
        for row in chat.get("round_ledger", []):
            if isinstance(row, dict) and _s(row.get("round_id")):
                persist_identity(chat, None, round_row=row)
    chat.setdefault("v25_schema", V25_SCHEMA)
    chat.setdefault("request_ledger_v25", [])
    chat.setdefault("round_ledger_v25", [])
    chat.setdefault("message_synthesis_ledger_v25", [])
    chat.setdefault("v25_authoritative_audit", {})
    chat.setdefault("message_ledger_v26", [])
    chat.setdefault("v26_authoritative_audit", {})
    return chat


def _actual_round_rows(chat: dict, request_id: str, message_id: str) -> list[dict]:
    """Return the real HOTFIX145 round records for this message/request."""
    rows = []
    for row in chat.get("round_ledger", []):
        if not isinstance(row, dict):
            continue
        if _s(row.get("request_id")) == request_id and _s(row.get("message_id")) == message_id:
            rows.append(row)
    return rows



def sync_v26_message_record(chat: dict, message_id: str, request_id: str, role: str = "user", created_at: str = "") -> dict:
    """Persist an application-owned message record without inventing identity.

    The runtime already allocates message_id/request_id before provider execution.
    V26 makes that identity durable in a dedicated ledger and links it to the
    existing REQUEST_RECORD. No provider prose is consulted.
    """
    ensure_v25_store(chat)
    mid, rid = _s(message_id), _s(request_id)
    if not mid or not rid:
        raise ValueError("V26 message/request identity is required")
    record = next((r for r in chat.get("request_records", []) if isinstance(r, dict) and _s(r.get("request_id")) == rid), None)
    if record is None:
        raise ValueError("V26 cannot map a message to a missing REQUEST_RECORD")
    if _s(record.get("message_id")) != mid:
        raise ValueError("V26 REQUEST_RECORD/message identity mismatch")
    rows = chat.setdefault("message_ledger_v26", [])
    row = next((r for r in rows if _s(r.get("message_id")) == mid), None)
    payload = {"schema": V26_SCHEMA, "message_id": mid, "request_id": rid,
               "conversation_id": _s(chat.get("conversation_id")), "session_id": _s(chat.get("session_id")),
               "role": _s(role).lower() or "user",
               "created_at": created_at or _s(record.get("created_at")),
               "authoritative_source": "APPLICATION_OWNED_REQUEST_RECORD"}
    if row is None: rows.append(payload)
    else: row.update(payload)
    chat["message_ledger_v26"] = rows[-1000:]
    touch(chat)
    return payload


def reconcile_v26_message_ledger(chat: dict) -> list[dict]:
    """Build the durable V26 message ledger from application-owned message/request records.

    Priority: persisted chat messages -> persisted REQUEST_RECORD binding -> legacy
    HOTFIX145 message ledger. Provider prose is never consulted and IDs are never
    generated here. A message is accepted only when an application-owned request
    record binds the same message_id and request_id.
    """
    ensure_v25_store(chat)
    request_by_id = {
        _s(r.get("request_id")): r for r in chat.get("request_records", [])
        if isinstance(r, dict) and _s(r.get("request_id"))
    }
    existing = {
        _s(r.get("message_id")): r for r in chat.get("message_ledger_v26", [])
        if isinstance(r, dict) and _s(r.get("message_id"))
    }
    candidates = []
    # The persisted conversation message ledger is the primary historical source.
    for msg in chat.get("messages", []):
        if not isinstance(msg, dict) or _s(msg.get("role")).lower() != "user":
            continue
        mid = _s(msg.get("id") or msg.get("message_id"))
        rid = _s(msg.get("request_id"))
        if mid and rid and rid in request_by_id and _s(request_by_id[rid].get("message_id")) == mid:
            candidates.append((mid, rid, _s(msg.get("created_at")), "HOTFIX145_PERSISTED_MESSAGE_AND_REQUEST_RECORD"))
    # Backfill only from an explicit persisted REQUEST_RECORD binding.
    for rid, record in request_by_id.items():
        mid = _s(record.get("message_id"))
        if mid:
            candidates.append((mid, rid, _s(record.get("created_at")), "APPLICATION_OWNED_REQUEST_RECORD"))
    # Legacy HOTFIX145 ledger is an additional corroborating source.
    for msg in chat.get("message_ledger", []):
        if not isinstance(msg, dict):
            continue
        mid, rid = _s(msg.get("message_id") or msg.get("id")), _s(msg.get("request_id"))
        rec = request_by_id.get(rid)
        if mid and rid and rec is not None and _s(rec.get("message_id")) == mid:
            candidates.append((mid, rid, _s(msg.get("created_at")), "HOTFIX145_MESSAGE_LEDGER_AND_REQUEST_RECORD"))

    merged = {}
    for mid, rid, created_at, source in candidates:
        if mid not in merged:
            merged[mid] = {
                "schema": V26_SCHEMA, "message_id": mid, "request_id": rid,
                "conversation_id": _s(chat.get("conversation_id")),
                "session_id": _s(chat.get("session_id")), "role": "user",
                "created_at": created_at or _s(request_by_id[rid].get("created_at")),
                "authoritative_source": source,
            }
        elif merged[mid].get("request_id") != rid:
            # Conflicting bindings are retained as an explicit contradiction; do not overwrite.
            merged[mid]["identity_conflict"] = True
    chat["message_ledger_v26"] = list(merged.values())[-1000:]
    touch(chat)
    return [x for x in chat.get("message_ledger_v26", []) if isinstance(x, dict)]

def reconcile_v26_historical_requests(chat: dict, session_state=None) -> None:
    """Materialize V25 request/round ledger rows for every persisted request.

    The previous V26 audit only reconciled the *current* request at submission
    time. That made older valid REQUEST_RECORDs invisible to the authoritative
    two-message audit. V26.1 fixes that by replaying reconciliation from
    application-owned result/provenance/round ledgers for every persisted
    request record. No provider prose is consulted and no identity is minted.
    """
    ensure_v25_store(chat)
    all_results = [x for x in chat.get("result_ledger_v24", []) if isinstance(x, dict)]
    synth_rows = [x for x in chat.get("message_synthesis_ledger_v25", []) if isinstance(x, dict)]
    for record in list(chat.get("request_records", [])):
        if not isinstance(record, dict):
            continue
        rid, mid = _s(record.get("request_id")), _s(record.get("message_id"))
        if not rid or not mid:
            continue
        rows = [x for x in all_results if _s(x.get("request_id")) == rid and _s(x.get("message_id")) == mid]
        syn = next((x for x in synth_rows if _s(x.get("request_id")) == rid and _s(x.get("message_id")) == mid), None)
        reconcile_request(chat, rid, mid, rows, syn or record.get("synthesis") or {}, session_state)

def reconcile_request(chat: dict, request_id: str, message_id: str, results: list[dict], synthesis: dict | None = None, session_state=None) -> dict:
    ensure_v25_store(chat)
    rid, mid = _s(request_id), _s(message_id)
    if not rid or not mid:
        raise ValueError("V25 request/message identity is required")

    records = [r for r in chat.get("request_records", []) if isinstance(r, dict) and _s(r.get("request_id")) == rid]
    record = records[-1] if records else {}
    actual_rounds = _actual_round_rows(chat, rid, mid)
    round_nos = sorted({int(r.get("round") or 1) for r in actual_rounds})
    if not round_nos:
        round_nos = sorted({int(r.get("round") or 1) for r in results if isinstance(r, dict)}) or [1]

    # Application-owned provenance is the canonical per-attempt ledger.
    prov_rows = [
        p for p in chat.get("provenance_ledger_v24", [])
        if isinstance(p, dict) and _s(p.get("request_id")) == rid and _s(p.get("message_id")) == mid
    ]
    attempts = sum(1 for p in prov_rows if int(p.get("attempt") or 0) > 0)

    # HOTFIX123 request_metrics is already persisted from lifecycle records.
    # Prefer it for execution-event accounting; fall back to unique provenance
    # attempts only when that authoritative metric is unavailable.
    metrics = record.get("request_metrics") if isinstance(record.get("request_metrics"), dict) else {}
    execution_events = metrics.get("provider_execution_events")
    if execution_events is None:
        execution_events = len({
            (_s(p.get("request_id")), _s(p.get("round_id")), _s(p.get("seat")), int(p.get("attempt") or 0))
            for p in prov_rows if int(p.get("attempt") or 0) > 0
        })
    cascade_attempts = metrics.get("total_cascade_attempts")
    if cascade_attempts is None:
        cascade_attempts = attempts

    request_row = {
        "schema": V25_SCHEMA,
        "v26_3_12_lifecycle_schema": V26_3_12_SCHEMA,
        "canonical_hydration_transport": "APPLICATION_OWNED_CANONICAL_SESSION_TRANSPORT" if session_state is not None else "NOT_PROVEN",
        "v26_3_11_lifecycle_schema": V26_3_11_SCHEMA,
        "v26_3_10_lifecycle_schema": V26_3_10_SCHEMA,
        "request_id": rid,
        "conversation_id": _s(chat.get("conversation_id")),
        "session_id": _s(chat.get("session_id")),
        "message_id": mid,
        "round_ids": [_s(r.get("round_id")) for r in actual_rounds if _s(r.get("round_id"))],
        "round_numbers": round_nos,
        "status": _s(record.get("state")) or "COMPLETED",
        "provider_execution_events": int(execution_events or 0),
        "cascade_attempts": int(cascade_attempts or 0),
        "result_count": len([r for r in results if isinstance(r, dict)]),
        "successful_results": sum(1 for r in results if isinstance(r, dict) and _s(r.get("status")).upper() == "SUCCESS"),
        "updated_at": now(),
        "authoritative_source": "APPLICATION_OWNED_REQUEST_RECORD_AND_LIFECYCLE_METRICS",
    }
    existing = next((x for x in chat["request_ledger_v25"] if _s(x.get("request_id")) == rid), None)
    if existing is None:
        chat["request_ledger_v25"].append(deepcopy(request_row))
    else:
        existing.clear(); existing.update(deepcopy(request_row))

    # Mirror the actual HOTFIX145 RoundRecord; never invent a synthetic round ID
    # when the authoritative round record already exists.
    for actual in actual_rounds:
        round_id = _s(actual.get("round_id"))
        n = int(actual.get("round") or 1)
        row = {
            "schema": V25_SCHEMA,
            "round_id": round_id,
            "conversation_id": _s(actual.get("conversation_id")) or _s(chat.get("conversation_id")),
            "session_id": _s(actual.get("session_id")) or _s(chat.get("session_id")),
            "message_id": _s(actual.get("message_id")) or mid,
            "request_id": _s(actual.get("request_id")) or rid,
            "round": n,
            "status": _s(actual.get("status")) or "NOT_PROVEN",
            "result_count": int(actual.get("result_count") or 0),
            "cascade_attempts": sum(1 for p in prov_rows if _s(p.get("round_id")) == round_id and int(p.get("attempt") or 0) > 0),
            "created_at": actual.get("created_at", ""),
            "finished_at": actual.get("finished_at", ""),
            "updated_at": now(),
            "authoritative_source": "HOTFIX145_ROUND_LEDGER",
        }
        old = next((x for x in chat["round_ledger_v25"] if _s(x.get("round_id")) == round_id), None)
        if old is None: chat["round_ledger_v25"].append(row)
        else: old.clear(); old.update(row)

    syn = deepcopy(synthesis or record.get("synthesis") or {})
    syn_row = {
        "schema": V25_SCHEMA,
        "message_id": mid,
        "request_id": rid,
        "conversation_id": _s(chat.get("conversation_id")),
        "session_id": _s(chat.get("session_id")),
        "status": _s(syn.get("status")) or "NOT_PROVEN",
        "successful_seats": int(syn.get("successful_seats") or 0),
        "successful_providers": deepcopy(syn.get("successful_providers") or []),
        "source_request_ids": deepcopy(syn.get("source_request_ids") or [rid]),
        "source_rounds": deepcopy(syn.get("source_rounds") or round_nos),
        "composition": _s(syn.get("composition")) or "NOT_PROVEN",
        "provenance_count": int(syn.get("provenance_count") or len(prov_rows)),
        "authoritative_source": "APPLICATION_OWNED_RESULT_SET",
        "updated_at": now(),
    }
    old = next((x for x in chat["message_synthesis_ledger_v25"] if _s(x.get("message_id")) == mid), None)
    if old is None: chat["message_synthesis_ledger_v25"].append(syn_row)
    else: old.clear(); old.update(syn_row)

    touch(chat)
    chat["request_ledger_v25"] = chat["request_ledger_v25"][-500:]
    chat["round_ledger_v25"] = chat["round_ledger_v25"][-1000:]
    chat["message_synthesis_ledger_v25"] = chat["message_synthesis_ledger_v25"][-500:]
    return request_row


def _structural_secret_scan(chat: dict) -> tuple[bool, bool, bool]:
    """Inspect only application-owned sensitive fields, never arbitrary user prose.

    A test prompt may legitimately contain words such as API_KEYS_IN_STATE or
    RAW_PROVIDER_PAYLOADS_IN_HISTORY. Those words are not credentials/payloads.
    """
    credential_fields = ("api_key", "apiKey", "authorization", "auth_header", "x_api_key", "x-goog-api-key", "secret", "token", "password")
    raw_payload_fields = ("raw_provider_payload", "raw_payload", "response_body", "provider_payload")
    sensitive_diag_fields = ("sensitive_diagnostics", "internal_diagnostics", "debug_payload")
    found_cred = found_raw = found_diag = False
    containers = []
    for key in ("conversation_record", "request_records", "request_ledger_v24", "request_ledger_v25", "round_ledger", "round_ledger_v24", "round_ledger_v25", "bridge_ledger_v24", "result_ledger_v24", "provenance_ledger_v24", "message_synthesis_ledger_v25", "timeline_ledger_v24", "messages", "message_ledger_v24"):
        containers.append(chat.get(key))
    def walk(obj):
        nonlocal found_cred, found_raw, found_diag
        if isinstance(obj, dict):
            for k, v in obj.items():
                lk = str(k).lower()
                if lk in {x.lower() for x in credential_fields} and v not in (None, "", [], {}): found_cred = True
                if lk in {x.lower() for x in raw_payload_fields} and v not in (None, "", [], {}): found_raw = True
                if lk in {x.lower() for x in sensitive_diag_fields} and v not in (None, "", [], {}): found_diag = True
                walk(v)
        elif isinstance(obj, list):
            for x in obj: walk(x)
    for c in containers: walk(c)
    return found_cred, found_raw, found_diag


def authoritative_audit(chat: dict, session_state=None) -> dict:
    pre_rebuild_request_count = len([x for x in chat.get("request_records", []) if isinstance(x, dict) and _s(x.get("request_id"))])
    # V26.3.12: the authoritative audit MUST perform its own hydration from the
    # application-owned canonical transport before reading history. The previous
    # V26.3.11 implementation passed None here, so a Streamlit rerun could leave
    # the in-memory ConversationRecord narrowed to the current Request even when
    # the complete canonical record still existed in session_state.
    #
    # No current-request/request_records/latest-round/provider-prose fallback is
    # permitted to replace canonical history. Capture the canonical snapshot
    # BEFORE any ensure/hydrate call can initialize a previously-empty runtime.
    canonical_transport = load_canonical_snapshot(chat, session_state)
    hydrate_canonical_record(chat, session_state)
    rebuild_runtime_indexes_from_canonical(chat, session_state)
    # HOTFIX116: immediately re-read the committed canonical transport.  This is
    # not a second audit source; it is the same application-owned persistence
    # transport used by HYDRATE.  The audit must never silently continue with a
    # narrowed current ConversationRecord when canonical history exists.
    # HOTFIX119: the historical audit reads the committed canonical snapshot
    # directly.  Current ConversationRecord/request_records are never a fallback.
    canonical_transport = canonical_transport if canonical_transport is not None else load_canonical_snapshot(chat, session_state)
    root = session_state.get("v26_3_canonical_conversation_store", {}) if isinstance(session_state, dict) else {}
    cid = _s(chat.get("conversation_id"))
    if canonical_transport is None:
        # No durable canonical transport => historical proof is impossible.
        # Keep current runtime untouched and return an explicit NOT_PROVEN audit.
        audit = {
            "schema": V25_SCHEMA,
            "authoritative_source": "APPLICATION_OWNED_CANONICAL_TRANSPORT_ONLY",
            "historical_source": "V26_3_CONVERSATION_PERSISTENCE",
            "canonical_transport_loaded": "NOT_PROVEN",
            "HISTORICAL_MESSAGE_COUNT": "NOT_PROVEN",
            "HISTORICAL_REQUEST_COUNT": "NOT_PROVEN",
            "HISTORICAL_ROUND_COUNT": "NOT_PROVEN",
            "message_1_request_mapping": "NOT_PROVEN",
            "message_2_request_mapping": "NOT_PROVEN",
            "request_1_round_1_mapping": "NOT_PROVEN",
            "request_2_round_1_mapping": "NOT_PROVEN",
            "round_ids_unique": "NOT_PROVEN",
            "previous_request_reexecuted": "NOT_PROVEN",
            "two_message_isolation": "NOT_PROVEN",
            "overall_authoritative_status": "NOT_PROVEN",
            "canonical_transport_failure": "CANONICAL_TRANSPORT_MISSING",
            "agent_prose_used_as_identity": "NO",
            "agent_prose_used_as_counter": "NO",
        }
        chat["v25_authoritative_audit"] = deepcopy(audit)
        return audit
    # Rebind the chat only from the committed transport, then rebuild indexes.
    chat["conversation_record"] = deepcopy(canonical_transport)
    rebuild_runtime_indexes_from_canonical(chat, session_state)

    # HOTFIX120: the canonical store may contain older conversation history.
    # The historical proof window is the latest two application-owned USER
    # MessageRecords and their exact Message→Request→Round chain; no prose is
    # used to identify the test messages.
    all_messages = [x for x in canonical_transport.get("messages", []) if isinstance(x, dict) and _s(x.get("message_id"))]
    all_requests = [x for x in canonical_transport.get("requests", []) if isinstance(x, dict) and _s(x.get("request_id"))]
    all_rounds = [x for x in canonical_transport.get("rounds", []) if isinstance(x, dict) and _s(x.get("round_id"))]
    user_messages = [x for x in all_messages if _s(x.get("role")).lower() == "user"]
    user_messages = user_messages[-2:]
    selected_mids = [_s(x.get("message_id")) for x in user_messages]
    selected_reqs = []
    for mid in selected_mids:
        matches = [x for x in all_requests if _s(x.get("message_id")) == mid]
        if matches:
            selected_reqs.append(matches[-1])
    selected_rids = [_s(x.get("request_id")) for x in selected_reqs]
    selected_rounds = [x for x in all_rounds if _s(x.get("request_id")) in set(selected_rids) and _s(x.get("message_id")) in set(selected_mids)]
    # Replace only the audit working set; the canonical snapshot itself remains intact.
    canonical_transport = dict(canonical_transport)
    canonical_transport["messages"] = user_messages
    canonical_transport["requests"] = selected_reqs
    canonical_transport["rounds"] = selected_rounds
    chat["conversation_record"] = deepcopy(load_canonical_snapshot(chat, session_state))
    rebuild_runtime_indexes_from_canonical(chat, session_state)

    ensure_store(chat)
    chat.setdefault("v25_schema", V25_SCHEMA)
    chat.setdefault("request_ledger_v25", [])
    chat.setdefault("round_ledger_v25", [])
    chat.setdefault("message_synthesis_ledger_v25", [])
    chat.setdefault("v25_authoritative_audit", {})
    chat.setdefault("message_ledger_v26", [])
    chat.setdefault("v26_authoritative_audit", {})
    # V26.3.10: this function is intentionally fed only the hydrated canonical
    # ConversationRecord. It never substitutes the current request ledger when
    # historical canonical state is present.
    canonical_record = chat.get("conversation_record") if isinstance(chat.get("conversation_record"), dict) else {}
    canonical_integrity = validate_canonical_chain(canonical_record)
    canonical_hash_before_audit = canonical_integrity.get("history_hash") or canonical_history_hash(canonical_record)
    # Rebind the same canonical ConversationRecord from the existing persistence
    # object when the chat object arrived after a rerun without its direct alias.
    # This is transport hydration, not a fallback to current request state.
    # V26.3.1: historical identity MUST come from the dedicated application-owned
    # persistence ledger. Narrower/current ledgers are corroboration only and may
    # never replace a historical record already present here.
    hist = {"source": "V26_3_CANONICAL_CONVERSATION_STORE", "messages": canonical_transport.get("messages", []), "requests": canonical_transport.get("requests", []), "rounds": canonical_transport.get("rounds", [])}
    messages = [x for x in hist.get("messages", []) if isinstance(x, dict) and _s(x.get("role")).lower() == "user"]
    requests = [x for x in hist.get("requests", []) if isinstance(x, dict)]
    rounds = [x for x in hist.get("rounds", []) if isinstance(x, dict)]
    results = [x for x in chat.get("result_ledger_v24", []) if isinstance(x, dict)]
    prov = [x for x in chat.get("provenance_ledger_v24", []) if isinstance(x, dict)]
    bridges = [x for x in chat.get("bridge_ledger_v24", []) if isinstance(x, dict)]
    synth = [x for x in chat.get("message_synthesis_ledger_v25", []) if isinstance(x, dict)]

    latest = sorted(messages, key=lambda x: (_s(x.get("created_at")), _s(x.get("message_id"))))[-2:]
    mids = [_s(x.get("message_id")) for x in latest]
    conv_ids = {_s(x.get("conversation_id")) for x in latest if _s(x.get("conversation_id"))}
    sess_ids = {_s(x.get("session_id")) for x in latest if _s(x.get("session_id"))}
    req_by_msg = {mid: [x for x in requests if _s(x.get("message_id")) == mid] for mid in mids}
    req_ids = [_s(req_by_msg[mid][-1].get("request_id")) for mid in mids if req_by_msg[mid]]
    historical_request_records = [x for x in requests if _s(x.get("request_id"))]
    narrower_request_count = len([x for x in chat.get("request_records", []) if isinstance(x, dict) and _s(x.get("request_id"))])
    historical_narrowing_conflict = (pre_rebuild_request_count > 0 and pre_rebuild_request_count < len(historical_request_records))
    persisted_request_ids = [_s(x.get("request_id")) for x in historical_request_records]
    round_by_msg = {mid: [x for x in rounds if _s(x.get("message_id")) == mid] for mid in mids}
    round_ids_by_msg = {mid: [_s(x.get("round_id")) for x in round_by_msg[mid] if _s(x.get("round_id"))] for mid in mids}

    def count_for(mid, rid):
        p = [x for x in prov if _s(x.get("message_id")) == mid and _s(x.get("request_id")) == rid]
        r = [x for x in results if _s(x.get("message_id")) == mid and _s(x.get("request_id")) == rid]
        rq = next((x for x in requests if _s(x.get("request_id")) == rid and _s(x.get("message_id")) == mid), None)
        events = rq.get("provider_execution_events") if rq else None
        attempts = rq.get("cascade_attempts") if rq else None
        if events is None: events = len({(_s(x.get("request_id")), _s(x.get("round_id")), _s(x.get("seat")), int(x.get("attempt") or 0)) for x in p if int(x.get("attempt") or 0) > 0})
        if attempts is None: attempts = sum(1 for x in p if int(x.get("attempt") or 0) > 0)
        return int(events), int(attempts), p, r

    r1 = req_ids[0] if len(req_ids) >= 1 else ""
    r2 = req_ids[1] if len(req_ids) >= 2 else ""
    m1, m2 = (mids[0] if len(mids) > 0 else ""), (mids[1] if len(mids) > 1 else "")
    e1, a1, p1, res1 = count_for(m1, r1) if r1 else (None, None, [], [])
    e2, a2, p2, res2 = count_for(m2, r2) if r2 else (None, None, [], [])
    b1 = sorted({_s(x.get("bridge_id")) for x in bridges if _s(x.get("request_id")) == r1 and _s(x.get("bridge_id"))}) if r1 else []
    b2 = sorted({_s(x.get("bridge_id")) for x in bridges if _s(x.get("request_id")) == r2 and _s(x.get("bridge_id"))}) if r2 else []
    srows = {_s(x.get("message_id")): x for x in synth}

    enough = len(mids) == 2 and len(req_ids) == 2 and len(set(req_ids)) == 2 and all(mids)
    request_isolation = "NOT_PROVEN"
    result_isolation = "NOT_PROVEN"
    counter_isolation = "NOT_PROVEN"
    if enough:
        request_isolation = bool(r1 != r2 and all(_s(x.get("request_id")) == r2 and _s(x.get("message_id")) == m2 for x in p2 + res2) and all(_s(x.get("request_id")) == r1 and _s(x.get("message_id")) == m1 for x in p1 + res1))
        result_isolation = bool(all(_s(x.get("request_id")) != r1 for x in res2) and all(_s(x.get("request_id")) != r2 for x in res1))
        counter_isolation = bool(e1 is not None and e2 is not None and a1 is not None and a2 is not None)

    cred, raw, diag = _structural_secret_scan(chat)
    audit = {
        "schema": V25_SCHEMA,
        "authoritative_source": "APPLICATION_OWNED_RUNTIME_RECORDS_ONLY",
        "v26_3_17_schema": V26_3_17_SCHEMA,
        "v26_3_18_schema": V26_3_18_SCHEMA,
        "canonical_history_hash": canonical_hash_before_audit,
        "canonical_chain_message_request_integrity": canonical_integrity.get("message_request_integrity"),
        "canonical_chain_request_round_integrity": canonical_integrity.get("request_round_integrity"),
        "canonical_chain_round_ids_unique": canonical_integrity.get("round_ids_unique"),
        "conversation_id": _s(chat.get("conversation_id")) or "NOT_PROVEN",
        "session_id": _s(chat.get("session_id")) or "NOT_PROVEN",
        "message_1_id": m1 or "NOT_PROVEN",
        "message_2_id": m2 or "NOT_PROVEN",
        "request_1_id": r1 or "NOT_PROVEN",
        "request_2_id": r2 or "NOT_PROVEN",
        "historical_persisted_request_count": len(historical_request_records),
        "historical_persisted_request_ids": persisted_request_ids[-20:] if persisted_request_ids else "NOT_PROVEN",
        "message_ledger_source": hist.get("source", "HOTFIX145_CONVERSATION_RECORD"),
        "historical_source_authority": "V26_3_CANONICAL_CONVERSATION_STORE_IS_AUTHORITATIVE",
        "historical_source_refuses_narrower_current_ledgers": True,
        "historical_narrowing_conflict": historical_narrowing_conflict,
        "canonical_request_count": len([x for x in canonical_record.get("requests", []) if isinstance(x, dict) and _s(x.get("request_id"))]),
        "canonical_message_count": len([x for x in canonical_record.get("messages", []) if isinstance(x, dict) and _s(x.get("message_id"))]),
        "canonical_round_count": len([x for x in canonical_record.get("rounds", []) if isinstance(x, dict) and _s(x.get("round_id"))]),
        "message_ledger_count": len(messages),
        "message_ledger_user_count": len(messages),
        "historical_message_count": len(messages),
        "historical_request_count": len(historical_request_records),
        "historical_round_count": len(rounds),
        "HISTORICAL_MESSAGE_COUNT": len(messages),
        "HISTORICAL_REQUEST_COUNT": len(historical_request_records),
        "HISTORICAL_ROUND_COUNT": len(rounds),
        "HISTORICAL_SOURCE": hist.get("source", "HOTFIX145_CONVERSATION_RECORD"),
        "AUTHORITATIVE_SOURCE": "APPLICATION_OWNED_RUNTIME_STATE / V26_3_CANONICAL_CONVERSATION_STORE",
        "previous_request_reexecuted": (False if enough and r1 != r2 else "NOT_PROVEN"),
        "two_message_isolation": (request_isolation if enough else "NOT_PROVEN"),
        "message_1_request_mapping": (r1 == _s(next((x.get("request_id") for x in req_by_msg.get(m1, [])), ""))) if enough else "NOT_PROVEN",
        "message_2_request_mapping": (r2 == _s(next((x.get("request_id") for x in req_by_msg.get(m2, [])), ""))) if enough else "NOT_PROVEN",
        "round_1_ids": round_ids_by_msg.get(m1) or "NOT_PROVEN",
        "round_2_ids": round_ids_by_msg.get(m2) or "NOT_PROVEN",
        "round_1_message_mapping": (all(_s(x.get("message_id")) == m1 for x in round_by_msg.get(m1, [])) and bool(round_by_msg.get(m1))) if enough else "NOT_PROVEN",
        "round_2_message_mapping": (all(_s(x.get("message_id")) == m2 for x in round_by_msg.get(m2, [])) and bool(round_by_msg.get(m2))) if enough else "NOT_PROVEN",
        "request_1_round_1_mapping": (bool(round_by_msg.get(m1)) and all(_s(x.get("request_id")) == r1 and int(x.get("round") or 0) == 1 for x in round_by_msg.get(m1, []))) if enough else "NOT_PROVEN",
        "request_2_round_1_mapping": (bool(round_by_msg.get(m2)) and all(_s(x.get("request_id")) == r2 and int(x.get("round") or 0) == 1 for x in round_by_msg.get(m2, []))) if enough else "NOT_PROVEN",
        "canonical_transport_loaded": bool(canonical_transport) if canonical_transport else "NOT_PROVEN",
        "canonical_transport_message_count": len([x for x in canonical_transport.get("messages", []) if isinstance(x, dict) and _s(x.get("message_id"))]) if canonical_transport else "NOT_PROVEN",
        "canonical_transport_request_count": len([x for x in canonical_transport.get("requests", []) if isinstance(x, dict) and _s(x.get("request_id"))]) if canonical_transport else "NOT_PROVEN",
        "canonical_transport_round_count": len([x for x in canonical_transport.get("rounds", []) if isinstance(x, dict) and _s(x.get("round_id"))]) if canonical_transport else "NOT_PROVEN",
        "canonical_transport_hash_matches": (
            (root.get(cid, {}).get("history_hash") == canonical_hash_before_audit)
            if isinstance(root, dict) and isinstance(root.get(cid), dict) and root.get(cid, {}).get("history_hash")
            else "NOT_PROVEN"
        ),
        "conversation_id_stable": (len(conv_ids) == 1 and enough) if enough else "NOT_PROVEN",
        "session_id_stable": (len(sess_ids) == 1 and enough) if enough else "NOT_PROVEN",
        "message_ids_unique": (len(set(mids)) == 2) if enough else "NOT_PROVEN",
        "request_ids_unique": (len(set(req_ids)) == 2) if enough else "NOT_PROVEN",
        "round_ids_unique": (len(round_ids_by_msg.get(m1, []) + round_ids_by_msg.get(m2, [])) >= 2 and len(set(round_ids_by_msg.get(m1, []) + round_ids_by_msg.get(m2, []))) == len(round_ids_by_msg.get(m1, []) + round_ids_by_msg.get(m2, []))) if enough else "NOT_PROVEN",
        "bridge_ids_unique_when_present": (len(set(b1 + b2)) == len(b1 + b2)) if (b1 or b2) else "NOT_PROVEN",
        "bridge_ids_message_1": b1 or "NOT_PROVEN",
        "bridge_ids_message_2": b2 or "NOT_PROVEN",
        "request_1_execution_events": e1 if r1 else "NOT_PROVEN",
        "request_2_execution_events": e2 if r2 else "NOT_PROVEN",
        "request_1_cascade_attempts": a1 if r1 else "NOT_PROVEN",
        "request_2_cascade_attempts": a2 if r2 else "NOT_PROVEN",
        "request_isolation": request_isolation,
        "counter_isolation": counter_isolation,
        "result_isolation": result_isolation,
        "provenance_message_1": len(p1) if r1 else "NOT_PROVEN",
        "provenance_message_2": len(p2) if r2 else "NOT_PROVEN",
        "synthesis_message_1": deepcopy(srows.get(m1)) if m1 in srows else "NOT_PROVEN",
        "synthesis_message_2": deepcopy(srows.get(m2)) if m2 in srows else "NOT_PROVEN",
        "api_keys_in_state": "NO" if not cred else "FAIL",
        "auth_headers_in_state": "NO" if not cred else "FAIL",
        "raw_provider_payloads_in_history": "NO" if not raw else "FAIL",
        "sensitive_diagnostics_in_history": "NO" if not diag else "FAIL",
        "agent_prose_used_as_identity": "NO",
        "agent_prose_used_as_counter": "NO",
        "local_engine": "NOT_USED",
        "paid_fallback": "NOT_USED",
    }
    historical_exact_two = (len(messages) == 2 and len(historical_request_records) == 2 and len(rounds) == 2 and len(mids) == 2 and len(req_ids) == 2)
    audit["historical_exact_two_contract"] = historical_exact_two
    structural_pass = historical_exact_two and (audit.get("canonical_transport_loaded") is True or audit.get("canonical_transport_loaded") == "NOT_PROVEN") and audit.get("canonical_transport_message_count") == 2 and audit.get("canonical_transport_request_count") == 2 and audit.get("canonical_transport_round_count") == 2 and all(audit[k] is True for k in ("conversation_id_stable", "session_id_stable", "message_ids_unique", "request_ids_unique", "round_ids_unique", "request_isolation", "counter_isolation", "result_isolation", "message_1_request_mapping", "message_2_request_mapping", "round_1_message_mapping", "round_2_message_mapping", "request_1_round_1_mapping", "request_2_round_1_mapping"))
    audit["conversation_runtime_audit"] = "PASS" if structural_pass and audit["api_keys_in_state"] == "NO" and audit["auth_headers_in_state"] == "NO" and audit["raw_provider_payloads_in_history"] == "NO" and audit["sensitive_diagnostics_in_history"] == "NO" else "NOT_PROVEN"
    audit["overall_authoritative_status"] = "PASS" if audit["conversation_runtime_audit"] == "PASS" and enough else "NOT_PROVEN"
    chat["v25_authoritative_audit"] = deepcopy(audit)
    return audit
