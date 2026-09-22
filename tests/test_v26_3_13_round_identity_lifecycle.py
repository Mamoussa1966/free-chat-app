from conversation_store import ensure_store, canonical_upsert_message, canonical_upsert_request, hydrate_canonical_record, rebuild_runtime_indexes_from_canonical
from conversation_runtime import begin_round, finish_round
from conversation_v25_runtime import authoritative_audit


def test_two_request_rerun_hydrate_rebuild_preserves_two_unique_round_records():
    chat = {"conversation_id":"conv-313","session_id":"sess-313","messages":[],"request_records":[],"round_ledger":[],"message_ledger":[],"conversation_record":{}}
    ensure_store(chat)
    session = {}
    ids = []
    for i in (1, 2):
        mid, rid = f"msg{i}", f"req{i}"
        canonical_upsert_message(chat, {"message_id":mid,"request_id":rid,"role":"user","conversation_id":"conv-313","session_id":"sess-313"}, session)
        canonical_upsert_request(chat, {"request_id":rid,"message_id":mid,"conversation_id":"conv-313","session_id":"sess-313","state":"RUNNING"}, session)
        oid = begin_round(chat, mid, rid, 1, session)
        finish_round(chat, oid, "COMPLETED", 2, session)
        ids.append(oid)
    assert ids[0] != ids[1]

    # Exact rerun failure simulation: current runtime narrows to Request 2 only.
    chat["conversation_record"] = {"conversation_id":"conv-313","session_id":"sess-313",
        "messages":[{"message_id":"msg2","request_id":"req2","role":"user"}],
        "requests":[{"request_id":"req2","message_id":"msg2"}],
        "rounds":[{"round_id":ids[1],"request_id":"req2","message_id":"msg2","round":1}]}
    chat["request_records"] = chat["conversation_record"]["requests"][:]
    chat["round_ledger"] = chat["conversation_record"]["rounds"][:]
    chat["message_ledger"] = []

    hydrate_canonical_record(chat, session)
    rebuild_runtime_indexes_from_canonical(chat, session)
    audit = authoritative_audit(chat, session)

    assert audit["HISTORICAL_MESSAGE_COUNT"] == 2
    assert audit["HISTORICAL_REQUEST_COUNT"] == 2
    assert audit["HISTORICAL_ROUND_COUNT"] == 2
    assert audit["message_1_request_mapping"] is True
    assert audit["message_2_request_mapping"] is True
    assert audit["round_1_message_mapping"] is True
    assert audit["round_2_message_mapping"] is True
    assert audit["round_ids_unique"] is True
    assert audit["overall_authoritative_status"] == "PASS"
    assert audit["round_1_ids"] == [ids[0]]
    assert audit["round_2_ids"] == [ids[1]]
