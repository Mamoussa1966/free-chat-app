from conversation_store import ensure_store, canonical_upsert_message, canonical_upsert_request, canonical_upsert_round, commit_canonical_record, hydrate_canonical_record
from conversation_v25_runtime import authoritative_audit

class SS(dict):
    pass

def add_chain(chat, ss, n):
    mid=f"m{n}"; rid=f"r{n}"; oid=f"round-{n}"
    canonical_upsert_message(chat,{"message_id":mid,"request_id":rid,"conversation_id":"conv","session_id":"sess","role":"user"},ss)
    canonical_upsert_request(chat,{"request_id":rid,"message_id":mid,"conversation_id":"conv","session_id":"sess","state":"COMPLETED"},ss)
    canonical_upsert_round(chat,{"round_id":oid,"request_id":rid,"message_id":mid,"conversation_id":"conv","session_id":"sess","round":1,"status":"COMPLETED"},ss)

def test_narrow_current_record_cannot_erase_canonical_history():
    ss=SS(); chat={"conversation_id":"conv","session_id":"sess","conversation_record":{}}; ensure_store(chat)
    add_chain(chat,ss,1)
    add_chain(chat,ss,2)
    saved=ss["v26_3_canonical_conversation_store"]["conv"]["record"]
    assert len(saved["messages"])==2 and len(saved["requests"])==2 and len(saved["rounds"])==2
    # Simulate Streamlit rerun exposing only current RequestRecord.
    narrow={"conversation_id":"conv","session_id":"sess","conversation_record":{"messages":saved["messages"][-1:],"requests":saved["requests"][-1:],"rounds":saved["rounds"][-1:]}}
    commit_canonical_record(narrow,ss)
    saved2=ss["v26_3_canonical_conversation_store"]["conv"]["record"]
    assert [x["request_id"] for x in saved2["requests"]]==["r1","r2"]
    assert [x["round_id"] for x in saved2["rounds"]]==["round-1","round-2"]

def test_hydration_rebuilds_indexes_from_full_canonical_record():
    ss=SS(); chat={"conversation_id":"conv","session_id":"sess","conversation_record":{}}; ensure_store(chat)
    add_chain(chat,ss,1); add_chain(chat,ss,2)
    fresh={"conversation_id":"conv","session_id":"sess","conversation_record":{}}
    hydrate_canonical_record(fresh,ss)
    idx=fresh["canonical_runtime_indexes"]
    assert idx["request_ids"]==["r1","r2"]
    assert idx["message_ids"]==["m1","m2"]
    assert idx["round_ids"]==["round-1","round-2"]

def test_authoritative_audit_never_falls_back_to_current_request():
    ss=SS(); chat={"conversation_id":"conv","session_id":"sess","conversation_record":{}}; ensure_store(chat)
    add_chain(chat,ss,1); add_chain(chat,ss,2)
    # Current/narrow ledger intentionally contains only request 2.
    chat["request_records"]=[{"request_id":"r2","message_id":"m2"}]
    a=authoritative_audit(chat)
    assert a["HISTORICAL_MESSAGE_COUNT"]==2
    assert a["HISTORICAL_REQUEST_COUNT"]==2
    assert a["HISTORICAL_ROUND_COUNT"]==2
    assert a["request_1_id"]=="r1" and a["request_2_id"]=="r2"
    assert a["authoritative_source"]=="APPLICATION_OWNED_RUNTIME_RECORDS_ONLY"
