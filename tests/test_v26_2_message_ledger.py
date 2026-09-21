import sys
sys.path.insert(0, '.')
from conversation_v25_runtime import authoritative_audit, ensure_v25_store


def _chat():
    c={"conversation_id":"c1","session_id":"s1","messages":[],"request_records":[],
       "message_ledger":[],"round_ledger":[],"result_ledger_v24":[],
       "provenance_ledger_v24":[],"bridge_ledger_v24":[],"message_synthesis_ledger_v25":[]}
    ensure_v25_store(c)
    return c


def test_two_message_historical_chain():
    c=_chat()
    for i in (1,2):
        mid=f"m{i}"; rid=f"r{i}"; qid=f"round{i}"
        c["messages"].append({"role":"user","id":mid,"request_id":rid,"created_at":f"2026-01-0{i}T00:00:00"})
        c["request_records"].append({"request_id":rid,"message_id":mid,"created_at":f"2026-01-0{i}T00:00:00","state":"COMPLETED","request_metrics":{"provider_execution_events":1,"total_cascade_attempts":1}})
        c["round_ledger"].append({"round_id":qid,"request_id":rid,"message_id":mid,"round":1,"status":"COMPLETED"})
        c["round_ledger_v25"].append({"round_id":qid,"request_id":rid,"message_id":mid,"round":1,"status":"COMPLETED"})
    a=authoritative_audit(c)
    assert a["message_1_id"]=="m1" and a["message_2_id"]=="m2"
    assert a["request_1_id"]=="r1" and a["request_2_id"]=="r2"
    assert a["message_1_request_mapping"] is True and a["message_2_request_mapping"] is True
    assert a["round_1_message_mapping"] is True and a["round_2_message_mapping"] is True
    assert a["request_ids_unique"] is True


def test_missing_message_binding_is_not_proven():
    c=_chat()
    c["messages"].append({"role":"user","id":"m1","request_id":"r1"})
    c["request_records"].append({"request_id":"r1","message_id":"m1"})
    a=authoritative_audit(c)
    assert a["overall_authoritative_status"]=="NOT_PROVEN"
