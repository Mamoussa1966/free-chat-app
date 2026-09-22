from conversation_store import ensure_store, canonical_upsert_message, canonical_upsert_request, canonical_upsert_round, hydrate_canonical_record, rebuild_runtime_indexes_from_canonical
from conversation_v25_runtime import authoritative_audit


def _append(chat, ss, n):
    mid, rid, oid = f"m{n}", f"req{n}", f"round-{n}"
    canonical_upsert_message(chat, {"message_id": mid, "request_id": rid, "conversation_id": "c", "session_id": "s", "role": "user", "created_at": f"2026-09-2{n}T00:00:00Z"}, ss)
    canonical_upsert_request(chat, {"request_id": rid, "message_id": mid, "conversation_id": "c", "session_id": "s", "state": "COMPLETED"}, ss)
    canonical_upsert_round(chat, {"round_id": oid, "request_id": rid, "message_id": mid, "conversation_id": "c", "session_id": "s", "round": 1, "status": "COMPLETED"}, ss)
    return mid, rid, oid


def test_hotfix118_full_roundtrip_survives_cleared_runtime_indexes():
    ss = {}
    chat = {"conversation_id": "c", "session_id": "s", "conversation_record": {}, "message_ledger": [], "request_records": [], "round_ledger": [], "messages": []}
    ensure_store(chat)
    a = _append(chat, ss, 1)
    # Simulate a Streamlit rerun before the second message: only canonical transport survives.
    chat["conversation_record"] = {"conversation_id": "c", "session_id": "s", "messages": [], "requests": [], "rounds": []}
    chat["message_ledger"], chat["request_records"], chat["round_ledger"] = [], [], []
    hydrate_canonical_record(chat, ss); rebuild_runtime_indexes_from_canonical(chat, ss)
    b = _append(chat, ss, 2)
    # Simulate the exact post-rerun narrow state that caused the historical failure.
    chat["conversation_record"] = {"conversation_id": "c", "session_id": "s", "messages": [chat["conversation_record"]["messages"][-1]], "requests": [chat["conversation_record"]["requests"][-1]], "rounds": [chat["conversation_record"]["rounds"][-1]]}
    chat["message_ledger"] = [chat["conversation_record"]["messages"][-1]]
    chat["request_records"] = [chat["conversation_record"]["requests"][-1]]
    chat["round_ledger"] = [chat["conversation_record"]["rounds"][-1]]
    hydrate_canonical_record(chat, ss); rebuild_runtime_indexes_from_canonical(chat, ss)
    audit = authoritative_audit(chat, ss)
    assert audit["HISTORICAL_MESSAGE_COUNT"] == 2
    assert audit["HISTORICAL_REQUEST_COUNT"] == 2
    assert audit["HISTORICAL_ROUND_COUNT"] == 2
    assert audit["message_1_request_mapping"] is True
    assert audit["message_2_request_mapping"] is True
    assert audit["request_1_round_1_mapping"] is True
    assert audit["request_2_round_1_mapping"] is True
    assert audit["round_ids_unique"] is True
    assert audit["previous_request_reexecuted"] is False
    assert audit["two_message_isolation"] is True
    assert audit["canonical_transport_hash_matches"] is True
    assert audit["overall_authoritative_status"] == "PASS"
