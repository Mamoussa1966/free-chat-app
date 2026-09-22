from conversation_store import ensure_store, canonical_upsert_message, canonical_upsert_request, canonical_upsert_round, hydrate_canonical_record, rebuild_runtime_indexes_from_canonical
from conversation_v25_runtime import authoritative_audit, reconcile_request


def base():
    return {"conversation_id":"conv-115","session_id":"sess-115","messages":[],"request_records":[],"round_ledger":[],"message_ledger":[],"conversation_record":{}}


def test_hotfix115_two_message_historical_contract_after_rerun_narrowing():
    chat=base(); ensure_store(chat); ss={}
    for i in (1,2):
        mid=f"msg{i}"; rid=f"req{i}"; oid=f"conv-115:{rid}:r1"
        canonical_upsert_message(chat,{"message_id":mid,"request_id":rid,"role":"user","conversation_id":"conv-115","session_id":"sess-115","created_at":f"2026-01-0{i}"},ss)
        canonical_upsert_request(chat,{"request_id":rid,"message_id":mid,"conversation_id":"conv-115","session_id":"sess-115","state":"COMPLETED"},ss)
        canonical_upsert_round(chat,{"round_id":oid,"request_id":rid,"message_id":mid,"conversation_id":"conv-115","session_id":"sess-115","round":1,"status":"COMPLETED"},ss)
    chat["conversation_record"]={"conversation_id":"conv-115","session_id":"sess-115","messages":[chat["conversation_record"]["messages"][1]],"requests":[chat["conversation_record"]["requests"][1]],"rounds":[chat["conversation_record"]["rounds"][1]]}
    chat["request_records"]=chat["conversation_record"]["requests"][:]
    chat["round_ledger"]=chat["conversation_record"]["rounds"][:]
    chat["message_ledger"]=chat["conversation_record"]["messages"][:]
    a=authoritative_audit(chat,ss)
    assert a["HISTORICAL_MESSAGE_COUNT"]==2
    assert a["HISTORICAL_REQUEST_COUNT"]==2
    assert a["HISTORICAL_ROUND_COUNT"]==2
    assert a["message_1_request_mapping"] is True
    assert a["message_2_request_mapping"] is True
    assert a["round_1_message_mapping"] is True
    assert a["round_2_message_mapping"] is True
    assert a["round_ids_unique"] is True
    assert a["previous_request_reexecuted"] is False
    assert a["two_message_isolation"] is True
    assert a["HISTORICAL_SOURCE"]=="V26_3_CONVERSATION_PERSISTENCE"
    assert a["AUTHORITATIVE_SOURCE"].startswith("APPLICATION_OWNED_RUNTIME_STATE")


def test_hotfix115_no_transport_never_falls_back_to_current_request():
    chat=base(); ensure_store(chat)
    chat["conversation_record"]={"conversation_id":"conv-115","session_id":"sess-115","messages":[{"message_id":"msg2","request_id":"req2","role":"user"}],"requests":[{"request_id":"req2","message_id":"msg2"}],"rounds":[{"round_id":"conv-115:req2:r1","request_id":"req2","message_id":"msg2","round":1}]}
    chat["request_records"]=chat["conversation_record"]["requests"][:]
    chat["round_ledger"]=chat["conversation_record"]["rounds"][:]
    a=authoritative_audit(chat,None)
    assert a["HISTORICAL_MESSAGE_COUNT"]==1
    assert a["HISTORICAL_REQUEST_COUNT"]==1
    assert a["HISTORICAL_ROUND_COUNT"]==1
    assert a["overall_authoritative_status"]=="NOT_PROVEN"
