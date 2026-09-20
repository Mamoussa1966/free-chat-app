from conversation_v25_runtime import ensure_v25_store, sync_v26_message_record, reconcile_v26_message_ledger, authoritative_audit, reconcile_request
from conversation_store import ensure_store
from conversation_runtime import begin_round, finish_round

def _result(rid, n=1):
    return {"request_id": rid, "round": 1, "seat": "gemini", "name": "Gemini", "executed_model": "gemini-test", "status": "SUCCESS", "attempt_telemetry": [{"attempt": 1, "model": "gemini-test", "status": "SUCCESS"}]}

def test_v26_persists_and_maps_two_messages():
    c={"id":"c","conversation_id":"conv","session_id":"sess","request_records":[]}
    ensure_store(c); ensure_v25_store(c)
    for i in (1,2):
        mid=f"m{i}"; rid=f"r{i}"
        c["request_records"].append({"request_id":rid,"message_id":mid,"state":"COMPLETED","created_at":f"2026-09-20T00:0{i}:00Z","synthesis":{}})
        sync_v26_message_record(c,mid,rid)
        round_id=begin_round(c,mid,rid,1); finish_round(c,round_id,"COMPLETED",1)
        reconcile_request(c,rid,mid,[_result(rid)],{})
    reconcile_v26_message_ledger(c)
    a=authoritative_audit(c)
    assert a["message_1_id"] == "m1" and a["message_2_id"] == "m2"
    assert a["request_1_id"] == "r1" and a["request_2_id"] == "r2"
    assert a["message_1_request_mapping"] is True and a["message_2_request_mapping"] is True
    assert a["round_1_message_mapping"] is True and a["round_2_message_mapping"] is True
    assert a["overall_authoritative_status"] == "PASS"

def test_v26_never_invents_missing_message_identity():
    c={"id":"c","conversation_id":"conv","session_id":"sess","request_records":[{"request_id":"r1","state":"COMPLETED"}]}
    ensure_store(c); ensure_v25_store(c)
    reconcile_v26_message_ledger(c)
    a=authoritative_audit(c)
    assert a["message_1_id"] == "NOT_PROVEN"
    assert a["overall_authoritative_status"] == "NOT_PROVEN"
