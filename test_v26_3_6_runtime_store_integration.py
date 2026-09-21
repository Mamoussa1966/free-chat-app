from conversation_store import ensure_store, persist_canonical, hydrate_canonical
from conversation_persistence_v26 import persist_identity, hydrate_chat_identity
from conversation_v25_runtime import authoritative_audit

class SS(dict): pass

def test_runtime_store_survives_narrow_current_ledger_and_hydrates_full_history():
    ss=SS()
    chat={"conversation_id":"conv-runtime","session_id":"sess","messages":[],"request_records":[],"round_ledger":[],"conversation_record":{}}
    ensure_store(chat)
    for i in (1,2):
        mid=f"m{i}"; rid=f"r{i}"; q=f"conv-runtime:{rid}:r1"
        msg={"message_id":mid,"request_id":rid,"conversation_id":"conv-runtime","session_id":"sess","role":"user"}
        req={"request_id":rid,"message_id":mid,"conversation_id":"conv-runtime","session_id":"sess","state":"COMPLETED"}
        rnd={"round_id":q,"request_id":rid,"message_id":mid,"conversation_id":"conv-runtime","session_id":"sess","round":1,"status":"COMPLETED"}
        persist_identity(chat,ss,message=msg,request=req,round_row=rnd)
    # Simulate exactly the failure mode seen in runtime: only current transient records remain.
    fresh={"conversation_id":"conv-runtime","session_id":"sess","messages":[],"request_records":[{"request_id":"r2","message_id":"m2"}],"round_ledger":[],"conversation_record":{}}
    hydrate_canonical(fresh,ss)
    hydrate_chat_identity(fresh,ss)
    a=authoritative_audit(fresh)
    assert a["message_1_id"]=="m1" and a["message_2_id"]=="m2"
    assert a["request_1_id"]=="r1" and a["request_2_id"]=="r2"
    assert a["HISTORICAL_MESSAGE_COUNT"]==2
    assert a["HISTORICAL_REQUEST_COUNT"]==2
    assert a["HISTORICAL_ROUND_COUNT"]==2
    assert a["round_ids_unique"] is True
    assert a["message_1_request_mapping"] is True and a["message_2_request_mapping"] is True
    assert a["historical_source_authority"]=="HOTFIX145_CONVERSATION_RECORD_IS_AUTHORITATIVE"
