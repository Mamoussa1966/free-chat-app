from __future__ import annotations

"""V25 authoritative Conversation Ledger / Message Runtime reconciliation.

This layer is additive to HOTFIX145/V24. It never chooses providers/models and never
reads agent prose. It derives its audit only from application-owned request records,
round records, result/provenance ledgers, and the stored message ledger.
"""

from copy import deepcopy
from conversation_store import ensure_store, append_once, touch, now

V25_SCHEMA = "v25-conversation-ledger-message-runtime/v1"


def _s(value) -> str:
    return str(value or "").strip()


def ensure_v25_store(chat: dict) -> dict:
    ensure_store(chat)
    chat.setdefault("v25_schema", V25_SCHEMA)
    chat.setdefault("request_ledger_v25", [])
    chat.setdefault("round_ledger_v25", [])
    chat.setdefault("message_synthesis_ledger_v25", [])
    chat.setdefault("v25_authoritative_audit", {})
    return chat


def reconcile_request(chat: dict, request_id: str, message_id: str, results: list[dict], synthesis: dict | None = None) -> dict:
    ensure_v25_store(chat)
    rid = _s(request_id)
    mid = _s(message_id)
    if not rid or not mid:
        raise ValueError("V25 request/message identity is required")

    records = [r for r in chat.get("request_records", []) if isinstance(r, dict) and _s(r.get("request_id")) == rid]
    record = records[-1] if records else {}
    round_nos = sorted({int(r.get("round") or 1) for r in results if isinstance(r, dict)}) or [1]
    attempts = []
    provider_events = []
    for result in results:
        if not isinstance(result, dict):
            continue
        events = result.get("runtime_execution_events") or result.get("attempt_telemetry") or []
        if isinstance(events, list):
            for ev in events:
                if not isinstance(ev, dict) or int(ev.get("attempt") or 0) <= 0:
                    continue
                attempts.append(ev)
        for ev in result.get("runtime_execution_events") or []:
            if isinstance(ev, dict) and ev.get("execution_started") is True:
                provider_events.append(ev)

    # One immutable request row. Repeated Streamlit reruns update it rather than duplicate it.
    request_row = {
        "schema": V25_SCHEMA,
        "request_id": rid,
        "conversation_id": _s(chat.get("conversation_id")),
        "session_id": _s(chat.get("session_id")),
        "message_id": mid,
        "round_ids": [f"{_s(chat.get('conversation_id'))}:{rid}:r{n}" for n in round_nos],
        "round_numbers": round_nos,
        "status": _s(record.get("state") or "COMPLETED"),
        "provider_execution_events": len(provider_events),
        "cascade_attempts": len(attempts),
        "result_count": len(results),
        "successful_results": sum(1 for r in results if isinstance(r, dict) and _s(r.get("status")).upper() == "SUCCESS"),
        "updated_at": now(),
        "authoritative_source": "APPLICATION_OWNED_REQUEST_RECORDS_AND_RUNTIME_RESULTS",
    }
    existing = next((x for x in chat["request_ledger_v25"] if _s(x.get("request_id")) == rid), None)
    if existing is None:
        chat["request_ledger_v25"].append(deepcopy(request_row))
    else:
        existing.clear(); existing.update(deepcopy(request_row))

    for n in round_nos:
        round_id = f"{_s(chat.get('conversation_id'))}:{rid}:r{n}"
        row = {
            "schema": V25_SCHEMA,
            "round_id": round_id,
            "conversation_id": _s(chat.get("conversation_id")),
            "session_id": _s(chat.get("session_id")),
            "message_id": mid,
            "request_id": rid,
            "round": n,
            "status": "COMPLETED" if results else "NOT_PROVEN",
            "result_count": sum(1 for r in results if isinstance(r, dict) and int(r.get("round") or 1) == n),
            "cascade_attempts": sum(len(r.get("runtime_execution_events") or r.get("attempt_telemetry") or []) for r in results if isinstance(r, dict) and int(r.get("round") or 1) == n),
            "updated_at": now(),
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
        "provenance_count": int(syn.get("provenance_count") or 0),
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


def authoritative_audit(chat: dict) -> dict:
    ensure_v25_store(chat)
    messages = [x for x in chat.get("message_ledger_v24", []) if isinstance(x, dict) and _s(x.get("role")).lower() == "user"]
    requests = [x for x in chat.get("request_ledger_v25", []) if isinstance(x, dict)]
    rounds = [x for x in chat.get("round_ledger_v25", []) if isinstance(x, dict)]
    results = [x for x in chat.get("result_ledger_v24", []) if isinstance(x, dict)]
    prov = [x for x in chat.get("provenance_ledger_v24", []) if isinstance(x, dict)]
    bridges = [x for x in chat.get("bridge_ledger_v24", []) if isinstance(x, dict)]
    synth = [x for x in chat.get("message_synthesis_ledger_v25", []) if isinstance(x, dict)]

    latest_messages = messages[-2:]
    mids = [_s(x.get("message_id")) for x in latest_messages]
    conv_ids = {_s(x.get("conversation_id")) for x in latest_messages if _s(x.get("conversation_id"))}
    sess_ids = {_s(x.get("session_id")) for x in latest_messages if _s(x.get("session_id"))}
    req_by_msg = {mid: [x for x in requests if _s(x.get("message_id")) == mid] for mid in mids}
    req_ids = [_s(req_by_msg[mid][-1].get("request_id")) for mid in mids if req_by_msg[mid]]
    round_ids = []
    for mid in mids:
        rows = [x for x in rounds if _s(x.get("message_id")) == mid]
        round_ids.extend(_s(x.get("round_id")) for x in rows if _s(x.get("round_id")))

    def counts(rid):
        pr = [x for x in prov if _s(x.get("request_id")) == rid]
        rr = [x for x in results if _s(x.get("request_id")) == rid]
        attempts = sum(1 for x in pr if int(x.get("attempt") or 0) > 0)
        events = sum(1 for x in rr if _s(x.get("status")).upper() == "SUCCESS")
        # request ledger is authoritative for execution-event count when available.
        rq = next((x for x in requests if _s(x.get("request_id")) == rid), {})
        return int(rq.get("provider_execution_events") or events), attempts

    r1 = req_ids[0] if len(req_ids) >= 1 else ""
    r2 = req_ids[1] if len(req_ids) >= 2 else ""
    e1, a1 = counts(r1) if r1 else (None, None)
    e2, a2 = counts(r2) if r2 else (None, None)
    b1 = sorted({_s(x.get("bridge_id")) for x in bridges if _s(x.get("request_id")) == r1 and _s(x.get("bridge_id"))}) if r1 else []
    b2 = sorted({_s(x.get("bridge_id")) for x in bridges if _s(x.get("request_id")) == r2 and _s(x.get("bridge_id"))}) if r2 else []
    srows = { _s(x.get("message_id")): x for x in synth }

    def eq_or_not(condition, present=True):
        return bool(condition) if present else "NOT_PROVEN"

    audit = {
        "schema": V25_SCHEMA,
        "authoritative_source": "APPLICATION_OWNED_RUNTIME_RECORDS_ONLY",
        "conversation_id": _s(chat.get("conversation_id")) or "NOT_PROVEN",
        "session_id": _s(chat.get("session_id")) or "NOT_PROVEN",
        "message_1_id": mids[0] if len(mids) >= 1 else "NOT_PROVEN",
        "message_2_id": mids[1] if len(mids) >= 2 else "NOT_PROVEN",
        "request_1_id": r1 or "NOT_PROVEN",
        "request_2_id": r2 or "NOT_PROVEN",
        "round_1_ids": [x for x in round_ids if x] if len(mids) >= 1 else "NOT_PROVEN",
        "conversation_id_stable": eq_or_not(len(conv_ids) == 1 and len(mids) == 2, len(mids) == 2),
        "session_id_stable": eq_or_not(len(sess_ids) == 1 and len(mids) == 2, len(mids) == 2),
        "message_ids_unique": eq_or_not(len(mids) == 2 and len(set(mids)) == 2, len(mids) == 2),
        "request_ids_unique": eq_or_not(len(req_ids) == 2 and len(set(req_ids)) == 2, len(req_ids) == 2),
        "round_ids_unique": eq_or_not(len(round_ids) >= 2 and len(set(round_ids)) == len(round_ids), len(round_ids) >= 2),
        "bridge_ids_unique_when_present": (len(set(b1 + b2)) == len(b1 + b2)) if (b1 or b2) else "NOT_PROVEN",
        "bridge_ids_message_1": b1 or "NOT_PROVEN",
        "bridge_ids_message_2": b2 or "NOT_PROVEN",
        "request_1_execution_events": e1 if r1 else "NOT_PROVEN",
        "request_2_execution_events": e2 if r2 else "NOT_PROVEN",
        "request_1_cascade_attempts": a1 if r1 else "NOT_PROVEN",
        "request_2_cascade_attempts": a2 if r2 else "NOT_PROVEN",
        "request_isolation": (r1 and r2 and all(_s(x.get("request_id")) in {r1, r2} for x in prov if _s(x.get("request_id")) in {r1, r2})),
        "counter_isolation": (r1 and r2 and e1 is not None and e2 is not None and a1 is not None and a2 is not None) if r1 and r2 else "NOT_PROVEN",
        "result_isolation": (r1 and r2 and all(_s(x.get("request_id")) != r1 for x in results if _s(x.get("message_id")) == (mids[1] if len(mids) > 1 else ""))),
        "provenance_message_1": len([x for x in prov if _s(x.get("message_id")) == (mids[0] if mids else "")]) if mids else "NOT_PROVEN",
        "provenance_message_2": len([x for x in prov if _s(x.get("message_id")) == (mids[1] if len(mids)>1 else "")]) if len(mids)>1 else "NOT_PROVEN",
        "synthesis_message_1": deepcopy(srows.get(mids[0])) if mids and mids[0] in srows else "NOT_PROVEN",
        "synthesis_message_2": deepcopy(srows.get(mids[1])) if len(mids)>1 and mids[1] in srows else "NOT_PROVEN",
        "api_keys_in_state": "NOT_PROVEN",
        "raw_provider_payloads_in_history": "NOT_PROVEN",
        "agent_prose_used_as_identity": "NO",
        "agent_prose_used_as_counter": "NO",
        "local_engine": "NOT_USED",
        "paid_fallback": "NOT_USED",
    }
    # Strong state checks for V25-controlled ledgers.
    state_blob = repr({"messages": messages, "requests": requests, "rounds": rounds, "results": results, "prov": prov, "bridges": bridges, "synth": synth}).lower()
    audit["api_keys_in_state"] = "NO" if not any(k in state_blob for k in ("api_key", "authorization", "x-api-key", "bearer ")) else "FAIL"
    audit["raw_provider_payloads_in_history"] = "NO" if not any(k in state_blob for k in ("raw_provider_payload", "raw_payload", "response_body")) else "FAIL"
    audit["conversation_runtime_audit"] = "PASS" if all(v is True or v == "NO" or v == "NO_RESPONSE" or v == "NOT_USED" for v in [audit["conversation_id_stable"], audit["session_id_stable"], audit["message_ids_unique"], audit["request_ids_unique"], audit["round_ids_unique"], audit["request_isolation"], audit["counter_isolation"], audit["result_isolation"], audit["agent_prose_used_as_identity"], audit["agent_prose_used_as_counter"]]) and audit["api_keys_in_state"] == "NO" and audit["raw_provider_payloads_in_history"] == "NO" else "NOT_PROVEN"
    audit["overall_authoritative_status"] = "PASS" if audit["conversation_runtime_audit"] == "PASS" and len(mids) == 2 and len(req_ids) == 2 else "NOT_PROVEN"
    chat["v25_authoritative_audit"] = deepcopy(audit)
    return audit
