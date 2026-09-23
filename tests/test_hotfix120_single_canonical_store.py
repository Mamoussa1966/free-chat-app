from conversation_store import ensure_store, canonical_upsert_message, canonical_upsert_request, canonical_upsert_round, load_canonical_snapshot, rebuild_runtime_indexes_from_canonical
from conversation_persistence_v26 import ensure_persistence_store, persist_identity, get_authoritative_bucket, persistence_audit
from conversation_v25_runtime import authoritative_audit


def add(chat, ss, i):
    mid=f"m{i}"; rid=f"r{i}"; oid=f"{chat['conversation_id']}:{rid}:r{i}"
    ts=f"2026-09-22T00:0{i}:00Z"
    persist_identity(chat, ss,
        message={"message_id":mid,"conversation_id":chat['conversation_id'],"session_id":chat['session_id'],"role":"user","request_id":rid,"created_at":ts},
        request={"request_id":rid,"message_id":mid,"conversation_id":chat['conversation_id'],"session_id":chat['session_id'],"state":"COMPLETED"},
        round_row={"round_id":oid,"request_id":rid,"message_id":mid,"conversation_id":chat['conversation_id'],"session_id":chat['session_id'],"round":i,"status":"COMPLETED","round_identity_contract":"V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1"})


def test_single_store_writer_and_reader_are_same_contract():
    ss={}; ensure_persistence_store(ss)
    chat={"conversation_id":"c","session_id":"s","conversation_record":{}}
    ensure_store(chat); add(chat,ss,1); add(chat,ss,2)
    snap=load_canonical_snapshot(chat,ss)
    bucket=get_authoritative_bucket(chat,ss)
    assert snap is not None and bucket is not None
    assert [x["request_id"] for x in snap["requests"]] == [x["request_id"] for x in bucket["requests"]]
    assert ss["v26_3_conversation_persistence"] is ss["v26_3_canonical_conversation_store"]
    assert persistence_audit(chat,ss)["source"] == "V26_3_CANONICAL_CONVERSATION_STORE"


def test_latest_two_message_chain_is_audited_from_canonical_store_even_with_older_history():
    ss={}; chat={"conversation_id":"c","session_id":"s","conversation_record":{}}
    ensure_store(chat)
    for i in range(1,6): add(chat,ss,i)
    # Simulate rerun narrowing runtime to Message 5 only.
    chat["request_records"]=[{"request_id":"r5","message_id":"m5"}]
    chat["round_ledger"]=[]
    a=authoritative_audit(chat,ss)
    assert a["HISTORICAL_MESSAGE_COUNT"] == 2
    assert a["HISTORICAL_REQUEST_COUNT"] == 2
    assert a["HISTORICAL_ROUND_COUNT"] == 2
    assert a["message_1_id"] == "m4" and a["message_2_id"] == "m5"
    assert a["request_1_id"] == "r4" and a["request_2_id"] == "r5"
    assert a["round_ids_unique"] is True
    assert a["message_1_request_mapping"] is True and a["message_2_request_mapping"] is True
    assert a["request_1_round_1_mapping"] is False and a["request_2_round_2_mapping"] is False
    assert a["request_2_round_1_mapping"] is False
    assert a["canonical_round_ordinals"] == [4, 5]
    assert a["canonical_round_sequence_proven"] is True
    assert a["canonical_round_identity_evidence"]["request_1_round_generic_exact"] is True
    assert a["canonical_round_identity_evidence"]["request_2_round_generic_exact"] is True
    assert a["overall_authoritative_status"] == "PASS"


def test_missing_canonical_store_is_fail_closed():
    chat={"conversation_id":"c","session_id":"s","conversation_record":{},"request_records":[{"request_id":"r2","message_id":"m2"}]}
    ensure_store(chat)
    chat["conversation_record"]["messages"]=[{"message_id":"m2","request_id":"r2","role":"user"}]
    chat["conversation_record"]["requests"]=[{"request_id":"r2","message_id":"m2"}]
    chat["conversation_record"]["rounds"]=[{"round_id":"c:r2:r2","request_id":"r2","message_id":"m2","round":2,"round_identity_contract":"V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1"}]
    # Not committed: authoritative history must not use current runtime as proof.
    a=authoritative_audit(chat,{})
    assert a["overall_authoritative_status"] == "NOT_PROVEN"
    assert a["HISTORICAL_MESSAGE_COUNT"] == "NOT_PROVEN"
