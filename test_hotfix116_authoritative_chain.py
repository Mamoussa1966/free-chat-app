from conversation_store import ensure_store, canonical_upsert_message, canonical_upsert_request, canonical_upsert_round, hydrate_canonical_record, rebuild_runtime_indexes_from_canonical
from conversation_v25_runtime import authoritative_audit


def test_hotfix116_request_round_message_chain_survives_rerun():
    chat = {"conversation_id":"conv-116","session_id":"sess-116","messages":[],"request_records":[],"round_ledger":[],"message_ledger":[],"conversation_record":{}}
    ss = {}
    ensure_store(chat)
    for i in (1, 2):
        mid, rid = f"msg{i}", f"req{i}"
        round_id = f"conv-116:{rid}:r{i}"
        canonical_upsert_message(chat, {"message_id":mid,"request_id":rid,"role":"user","conversation_id":"conv-116","session_id":"sess-116"}, ss)
        canonical_upsert_request(chat, {"request_id":rid,"message_id":mid,"conversation_id":"conv-116","session_id":"sess-116","state":"COMPLETED"}, ss)
        canonical_upsert_round(chat, {"round_id":round_id,"request_id":rid,"message_id":mid,"conversation_id":"conv-116","session_id":"sess-116","round":i,"status":"COMPLETED","round_identity_contract":"V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1"}, ss)

    # Simulate Streamlit rerun narrowing the live object to Message 2 only.
    chat["conversation_record"] = {
        "conversation_id":"conv-116", "session_id":"sess-116",
        "messages":[{"message_id":"msg2","request_id":"req2","role":"user"}],
        "requests":[{"request_id":"req2","message_id":"msg2"}],
        "rounds":[{"round_id":"conv-116:req2:r1","request_id":"req2","message_id":"msg2","round":2,"round_identity_contract":"V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1"}],
    }
    chat["request_records"] = chat["conversation_record"]["requests"][:]
    chat["round_ledger"] = chat["conversation_record"]["rounds"][:]
    chat["message_ledger"] = chat["conversation_record"]["messages"][:]

    hydrate_canonical_record(chat, ss)
    rebuild_runtime_indexes_from_canonical(chat, ss)
    audit = authoritative_audit(chat, ss)

    assert audit["HISTORICAL_MESSAGE_COUNT"] == 2
    assert audit["HISTORICAL_REQUEST_COUNT"] == 2
    assert audit["HISTORICAL_ROUND_COUNT"] == 2
    assert audit["request_1_id"] == "req1"
    assert audit["request_2_id"] == "req2"
    assert audit["round_ids_unique"] is True
    assert audit["message_1_request_mapping"] is True
    assert audit["message_2_request_mapping"] is True
    assert audit["request_1_round_1_mapping"] is True
    assert audit["request_2_round_2_mapping"] is True
    assert audit["request_2_round_1_mapping"] is False
    assert audit["previous_request_reexecuted"] is False
    assert audit["two_message_isolation"] is True
    assert audit["canonical_transport_loaded"] is True
    assert audit["canonical_transport_message_count"] == 2
    assert audit["canonical_transport_request_count"] == 2
    assert audit["canonical_transport_round_count"] == 2
    assert audit["overall_authoritative_status"] == "PASS"
