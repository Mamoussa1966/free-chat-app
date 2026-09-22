from conversation_store import ensure_store, canonical_upsert_message, canonical_upsert_request, canonical_upsert_round, hydrate_canonical_record, rebuild_runtime_indexes_from_canonical
from conversation_v25_runtime import authoritative_audit


def base():
    return {"conversation_id":"conv-test","session_id":"sess-test","messages":[],"request_records":[],"round_ledger":[],"message_ledger":[],"conversation_record":{}}


def test_rebuild_restores_two_message_request_round_chain():
    c=base(); ensure_store(c); ss={}
    for i in (1,2):
        mid=f"msg{i}"; rid=f"req{i}"; oid=f"conv-test:{rid}:r1"
        canonical_upsert_message(c,{"message_id":mid,"request_id":rid,"role":"user"},ss)
        canonical_upsert_request(c,{"request_id":rid,"message_id":mid,"state":"COMPLETED"},ss)
        canonical_upsert_round(c,{"round_id":oid,"request_id":rid,"message_id":mid,"round":1},ss)
    c["request_records"]= [c["conversation_record"]["requests"][-1]]
    c["round_ledger"]= [c["conversation_record"]["rounds"][-1]]
    c["message_ledger"]=[]
    hydrate_canonical_record(c,ss); rebuild_runtime_indexes_from_canonical(c,ss)
    assert len(c["request_records"])==2
    assert len(c["round_ledger"])==2
    assert len(c["message_ledger"])==2


def test_audit_reads_canonical_history_not_current_only():
    c=base(); ensure_store(c); ss={}
    for i in (1,2):
        mid=f"msg{i}"; rid=f"req{i}"; oid=f"conv-test:{rid}:r1"
        canonical_upsert_message(c,{"message_id":mid,"request_id":rid,"role":"user","created_at":f"2026-01-0{i}"},ss)
        canonical_upsert_request(c,{"request_id":rid,"message_id":mid},ss)
        canonical_upsert_round(c,{"round_id":oid,"request_id":rid,"message_id":mid,"round":1},ss)
    c["request_records"]= [c["conversation_record"]["requests"][-1]]
    c["round_ledger"]= [c["conversation_record"]["rounds"][-1]]
    a=authoritative_audit(c)
    assert a["HISTORICAL_MESSAGE_COUNT"]==2
    assert a["HISTORICAL_REQUEST_COUNT"]==2
    assert a["HISTORICAL_ROUND_COUNT"]==2
    assert a["request_1_id"]=="req1" and a["request_2_id"]=="req2"
    assert a["message_1_id"]=="msg1" and a["message_2_id"]=="msg2"
    assert a["round_ids_unique"] is True
