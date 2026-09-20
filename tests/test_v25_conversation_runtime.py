from conversation_v25_runtime import ensure_v25_store, reconcile_request, authoritative_audit
from conversation_store import ensure_store


def result(rid, round_no, seat="gemini", model="gemini-3.5-flash", attempts=2):
    events=[]
    for i in range(1, attempts+1):
        events.append({"attempt":i,"model":model if i==attempts else f"fallback-{i}","status":"SUCCESS" if i==attempts else "FAILED","classification":"SUCCESS" if i==attempts else "TRANSIENT_PROVIDER_ERROR","cascade_action":"SUCCESS" if i==attempts else "CASCADE_CONTINUE","execution_started":True})
    return {"request_id":rid,"round":round_no,"seat":seat,"name":"Gemini","executed_model":model,"model":model,"status":"SUCCESS","runtime_execution_events":events}


def test_two_messages_are_isolated_and_stable():
    chat={"id":"chat-test","conversation_id":"conv-fixed","session_id":"sess-fixed","request_records":[]}
    ensure_store(chat); ensure_v25_store(chat)
    chat["message_ledger_v24"]=[
        {"message_id":"m1","conversation_id":"conv-fixed","session_id":"sess-fixed","role":"user","user_input":"one"},
        {"message_id":"m2","conversation_id":"conv-fixed","session_id":"sess-fixed","role":"user","user_input":"two"},
    ]
    chat["request_records"]=[
        {"request_id":"r1","state":"COMPLETED","synthesis":{"status":"READY","successful_seats":1,"successful_providers":["Gemini"],"source_request_ids":["r1"],"source_rounds":[1],"composition":"APPLICATION_OWNED_RESULT_SET","provenance_count":2}},
        {"request_id":"r2","state":"COMPLETED","synthesis":{"status":"READY","successful_seats":1,"successful_providers":["Gemini"],"source_request_ids":["r2"],"source_rounds":[1],"composition":"APPLICATION_OWNED_RESULT_SET","provenance_count":1}},
    ]
    from provenance_engine import record_result
    from conversation_store import append_once
    for rid,mid in [("r1","m1"),("r2","m2")]:
        rr=result(rid,1,attempts=2 if rid=="r1" else 1)
        reconcile_request(chat,rid,mid,[rr],chat["request_records"][0 if rid=="r1" else 1]["synthesis"])
        record_result(chat,rr,mid,f"conv-fixed:{rid}:r1")
        append_once(chat["result_ledger_v24"],{"result_id":f"res-{rid}","request_id":rid,"message_id":mid,"provider":"Gemini","seat":"gemini","model":rr["executed_model"],"status":"SUCCESS","provenance_count":2},("result_id",))
    audit=authoritative_audit(chat)
    assert audit["conversation_id_stable"] is True
    assert audit["session_id_stable"] is True
    assert audit["message_ids_unique"] is True
    assert audit["request_ids_unique"] is True
    assert audit["round_ids_unique"] is True
    assert audit["request_isolation"]
    assert audit["result_isolation"]
    assert audit["agent_prose_used_as_identity"] == "NO"
    assert audit["agent_prose_used_as_counter"] == "NO"
    assert audit["overall_authoritative_status"] == "PASS"


def test_single_message_is_not_false_pass():
    chat={"id":"chat-test","conversation_id":"conv-fixed","session_id":"sess-fixed","request_records":[]}
    ensure_store(chat); ensure_v25_store(chat)
    chat["message_ledger_v24"]=[{"message_id":"m1","conversation_id":"conv-fixed","session_id":"sess-fixed","role":"user","user_input":"one"}]
    chat["request_records"]=[{"request_id":"r1","state":"COMPLETED","synthesis":{}}]
    reconcile_request(chat,"r1","m1",[result("r1",1) ],{})
    audit=authoritative_audit(chat)
    assert audit["message_2_id"] == "NOT_PROVEN"
    assert audit["request_2_id"] == "NOT_PROVEN"
    assert audit["overall_authoritative_status"] == "NOT_PROVEN"
