from collections import UserDict
from conversation_store import ensure_store, load_canonical_snapshot
from conversation_persistence_v26 import ensure_persistence_store, persist_identity, get_authoritative_bucket
from conversation_v25_runtime import authoritative_audit

class SessionMapping(UserDict):
    pass

def seed(chat, ss, i):
    mid=f"m{i}"; rid=f"r{i}"; oid=f"{chat['conversation_id']}:{rid}:round1"
    persist_identity(chat, ss,
      message={"message_id":mid,"request_id":rid,"conversation_id":chat['conversation_id'],"session_id":chat['session_id'],"role":"user","created_at":f"2026-09-23T00:0{i}:00Z"},
      request={"request_id":rid,"message_id":mid,"conversation_id":chat['conversation_id'],"session_id":chat['session_id'],"state":"COMPLETED"},
      round_row={"round_id":oid,"request_id":rid,"message_id":mid,"conversation_id":chat['conversation_id'],"session_id":chat['session_id'],"round":1,"status":"COMPLETED"})

def test_streamlit_like_mapping_uses_same_canonical_store_for_writer_reader_and_audit():
    ss=SessionMapping(); ensure_persistence_store(ss)
    chat={"conversation_id":"conv121","session_id":"sess121","conversation_record":{}}
    ensure_store(chat)
    seed(chat,ss,1); seed(chat,ss,2); seed(chat,ss,3)
    # Exact rerun narrowing: only Message 3 remains in transient runtime indexes.
    chat["request_records"]=[{"request_id":"r3","message_id":"m3"}]
    chat["round_ledger"]=[]
    snap=load_canonical_snapshot(chat,ss)
    bucket=get_authoritative_bucket(chat,ss)
    assert snap is not None and bucket is not None
    assert len(snap["requests"])==3 and len(bucket["requests"])==3
    audit=authoritative_audit(chat,ss)
    assert audit["HISTORICAL_MESSAGE_COUNT"]==2
    assert audit["HISTORICAL_REQUEST_COUNT"]==2
    assert audit["HISTORICAL_ROUND_COUNT"]==2
    assert audit["message_1_request_mapping"] is True
    assert audit["message_2_request_mapping"] is True
    assert audit["request_1_round_1_mapping"] is True
    assert audit["request_2_round_1_mapping"] is True
    assert audit["round_ids_unique"] is True
    assert audit["previous_request_reexecuted"] is False
    assert audit["two_message_isolation"] is True
    assert audit["canonical_transport_loaded"] is True
    assert audit["overall_authoritative_status"]=="PASS"

def test_uncommitted_current_record_is_not_historical_proof():
    chat={"conversation_id":"conv121-missing","session_id":"sess121","conversation_record":{},"request_records":[{"request_id":"r2","message_id":"m2"}]}
    ensure_store(chat)
    chat["conversation_record"]["messages"]=[{"message_id":"m2","request_id":"r2","role":"user"}]
    chat["conversation_record"]["requests"]=[{"request_id":"r2","message_id":"m2"}]
    chat["conversation_record"]["rounds"]=[{"round_id":"conv121-missing:r2:round1","request_id":"r2","message_id":"m2","round":1}]
    audit=authoritative_audit(chat,None)
    assert audit["HISTORICAL_MESSAGE_COUNT"]=="NOT_PROVEN"
    assert audit["HISTORICAL_REQUEST_COUNT"]=="NOT_PROVEN"
    assert audit["HISTORICAL_ROUND_COUNT"]=="NOT_PROVEN"
    assert audit["overall_authoritative_status"]=="NOT_PROVEN"
