from __future__ import annotations

"""V25 authoritative Conversation Ledger / Message Runtime.

Additive reconciliation layer on top of HOTFIX145/V24.  It consumes only
application-owned ledgers and persisted lifecycle/result metrics.  It never
selects providers/models and never treats provider prose as identity or
accounting evidence.
"""

from copy import deepcopy
from conversation_store import ensure_store, touch, now

V25_SCHEMA = "v25-conversation-ledger-message-runtime/v2"
V26_SCHEMA = "v26-message-runtime-authoritative-mapping/v1"


def _s(value) -> str:
    return str(value or "").strip()


def ensure_v25_store(chat: dict) -> dict:
    ensure_store(chat)
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
    """Reconcile only identities already present in application-owned request records.

    This is recovery of durable identity, not synthetic message creation.
    """
    ensure_v25_store(chat)
    for record in chat.get("request_records", []):
        if not isinstance(record, dict):
            continue
        mid, rid = _s(record.get("message_id")), _s(record.get("request_id"))
        if mid and rid:
            sync_v26_message_record(chat, mid, rid, "user", _s(record.get("created_at")))
    return [x for x in chat.get("message_ledger_v26", []) if isinstance(x, dict)]

def reconcile_request(chat: dict, request_id: str, message_id: str, results: list[dict], synthesis: dict | None = None) -> dict:
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


def authoritative_audit(chat: dict) -> dict:
    ensure_v25_store(chat)
    reconcile_v26_message_ledger(chat)
    messages = [x for x in chat.get("message_ledger_v26", []) if isinstance(x, dict) and _s(x.get("role")).lower() == "user"]
    requests = [x for x in chat.get("request_ledger_v25", []) if isinstance(x, dict)]
    rounds = [x for x in chat.get("round_ledger_v25", []) if isinstance(x, dict)]
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

    enough = len(mids) == 2 and len(req_ids) == 2
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
        "conversation_id": _s(chat.get("conversation_id")) or "NOT_PROVEN",
        "session_id": _s(chat.get("session_id")) or "NOT_PROVEN",
        "message_1_id": m1 or "NOT_PROVEN",
        "message_2_id": m2 or "NOT_PROVEN",
        "request_1_id": r1 or "NOT_PROVEN",
        "request_2_id": r2 or "NOT_PROVEN",
        "message_1_request_mapping": (r1 == _s(next((x.get("request_id") for x in req_by_msg.get(m1, [])), ""))) if enough else "NOT_PROVEN",
        "message_2_request_mapping": (r2 == _s(next((x.get("request_id") for x in req_by_msg.get(m2, [])), ""))) if enough else "NOT_PROVEN",
        "round_1_ids": round_ids_by_msg.get(m1) or "NOT_PROVEN",
        "round_2_ids": round_ids_by_msg.get(m2) or "NOT_PROVEN",
        "round_1_message_mapping": (all(_s(x.get("message_id")) == m1 for x in round_by_msg.get(m1, [])) and bool(round_by_msg.get(m1))) if enough else "NOT_PROVEN",
        "round_2_message_mapping": (all(_s(x.get("message_id")) == m2 for x in round_by_msg.get(m2, [])) and bool(round_by_msg.get(m2))) if enough else "NOT_PROVEN",
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
    structural_pass = all(audit[k] is True for k in ("conversation_id_stable", "session_id_stable", "message_ids_unique", "request_ids_unique", "round_ids_unique", "request_isolation", "counter_isolation", "result_isolation", "message_1_request_mapping", "message_2_request_mapping", "round_1_message_mapping", "round_2_message_mapping"))
    audit["conversation_runtime_audit"] = "PASS" if structural_pass and audit["api_keys_in_state"] == "NO" and audit["auth_headers_in_state"] == "NO" and audit["raw_provider_payloads_in_history"] == "NO" and audit["sensitive_diagnostics_in_history"] == "NO" else "NOT_PROVEN"
    audit["overall_authoritative_status"] = "PASS" if audit["conversation_runtime_audit"] == "PASS" and enough else "NOT_PROVEN"
    chat["v25_authoritative_audit"] = deepcopy(audit)
    return audit
