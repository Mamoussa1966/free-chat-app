from conversation_store import ensure_store, canonical_upsert_message, canonical_upsert_request, canonical_upsert_round, hydrate_canonical_record, rebuild_runtime_indexes_from_canonical
from conversation_v25_runtime import authoritative_audit


def _base():
    return {"conversation_id":"conv-rerun", "session_id":"sess-rerun", "messages":[], "request_records":[], "round_ledger":[], "message_ledger":[], "conversation_record":{}}


def test_authoritative_audit_hydrates_from_session_canonical_after_narrow_runtime_state():
    chat=_base(); ensure_store(chat); session_state={}
    for i in (1,2):
        mid=f"msg{i}"; rid=f"req{i}"; round_id=f"conv-rerun:{rid}:r{i}"
        canonical_upsert_message(chat,{"message_id":mid,"request_id":rid,"role":"user","conversation_id":"conv-rerun","session_id":"sess-rerun"},session_state)
        canonical_upsert_request(chat,{"request_id":rid,"message_id":mid,"conversation_id":"conv-rerun","session_id":"sess-rerun","state":"COMPLETED"},session_state)
        canonical_upsert_round(chat,{"round_id":round_id,"request_id":rid,"message_id":mid,"round":i,"conversation_id":"conv-rerun","session_id":"sess-rerun","round_identity_contract":"V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1"},session_state)

    # Simulate the exact failure mode observed after Streamlit rerun: current
    # in-memory state contains only Message 2 / Request 2 / Round 2's request.
    chat["conversation_record"]={"conversation_id":"conv-rerun","session_id":"sess-rerun",
        "messages":[{"message_id":"msg2","request_id":"req2","role":"user"}],
        "requests":[{"request_id":"req2","message_id":"msg2"}],
        "rounds":[{"round_id":"conv-rerun:req2:r2","request_id":"req2","message_id":"msg2","round":2,"round_identity_contract":"V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1"}]}
    chat["request_records"]=chat["conversation_record"]["requests"][:]
    chat["round_ledger"]=chat["conversation_record"]["rounds"][:]
    chat["message_ledger"]=[]

    audit=authoritative_audit(chat, session_state)
    assert audit["HISTORICAL_MESSAGE_COUNT"] == 2
    assert audit["HISTORICAL_REQUEST_COUNT"] == 2
    assert audit["HISTORICAL_ROUND_COUNT"] == 2
    assert audit["message_1_id"] == "msg1"
    assert audit["message_2_id"] == "msg2"
    assert audit["request_1_id"] == "req1"
    assert audit["request_2_id"] == "req2"
    assert audit["round_1_ids"] == ["conv-rerun:req1:r1"]
    assert audit["round_2_ids"] == ["conv-rerun:req2:r2"]
    assert audit["round_ids_unique"] is True
    assert audit["message_1_request_mapping"] is True
    assert audit["message_2_request_mapping"] is True
    assert audit["round_1_message_mapping"] is True
    assert audit["round_2_message_mapping"] is True
    assert audit["historical_exact_two_contract"] is True
    assert audit["overall_authoritative_status"] == "PASS"


def test_audit_without_canonical_transport_does_not_fallback_to_current_request():
    chat=_base(); ensure_store(chat)
    chat["conversation_record"]["messages"]=[{"message_id":"msg2","request_id":"req2","role":"user"}]
    chat["conversation_record"]["requests"]=[{"request_id":"req2","message_id":"msg2"}]
    chat["conversation_record"]["rounds"]=[{"round_id":"conv-rerun:req2:r2","request_id":"req2","message_id":"msg2","round":2,"round_identity_contract":"V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1"}]
    chat["request_records"]=chat["conversation_record"]["requests"][:]
    chat["round_ledger"]=chat["conversation_record"]["rounds"][:]
    audit=authoritative_audit(chat, None)
    assert audit["HISTORICAL_MESSAGE_COUNT"] == "NOT_PROVEN"
    assert audit["HISTORICAL_REQUEST_COUNT"] == "NOT_PROVEN"
    assert audit["HISTORICAL_ROUND_COUNT"] == "NOT_PROVEN"
    assert audit["overall_authoritative_status"] == "NOT_PROVEN"
