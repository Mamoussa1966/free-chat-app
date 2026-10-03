from conversation_store import ensure_store, canonical_upsert_message, canonical_upsert_request, canonical_upsert_round, load_canonical_snapshot, prepare_historical_runtime
from conversation_v25_runtime import authoritative_audit


def _chat():
    return {"conversation_id":"conv119","session_id":"sess119","conversation_record":{},"message_ledger":[],"request_records":[],"round_ledger":[],"messages":[]}


def _append(chat, ss, n):
    mid, rid, oid = f"m{n}", f"req{n}", f"conv119:{rid if False else f'req{n}'}:r{n}"
    canonical_upsert_message(chat, {"message_id":mid,"request_id":rid,"role":"user","conversation_id":"conv119","session_id":"sess119"}, ss)
    canonical_upsert_request(chat, {"request_id":rid,"message_id":mid,"conversation_id":"conv119","session_id":"sess119","state":"COMPLETED"}, ss)
    canonical_upsert_round(chat, {"round_id":oid,"request_id":rid,"message_id":mid,"conversation_id":"conv119","session_id":"sess119","round":n,"status":"COMPLETED","round_identity_contract":"V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1"}, ss)
    return mid, rid, oid


def test_message2_allocation_starts_from_durable_message1_snapshot():
    ss={}; chat=_chat(); ensure_store(chat)
    _append(chat, ss, 1)
    # Exact rerun state: only current Message 2-like runtime is present, while
    # canonical transport still owns Message 1.
    chat["conversation_record"]={"conversation_id":"conv119","session_id":"sess119","messages":[],"requests":[],"rounds":[]}
    chat["message_ledger"]=[]; chat["request_records"]=[]; chat["round_ledger"]=[]
    snap=prepare_historical_runtime(chat, ss)
    assert len(snap["messages"]) == 1
    assert snap["requests"][0]["request_id"] == "req1"
    assert snap["rounds"][0]["round_id"] != ""
    _append(chat, ss, 2)
    final=load_canonical_snapshot(chat, ss)
    assert len(final["messages"]) == 2
    assert len(final["requests"]) == 2
    assert len(final["rounds"]) == 2
    assert final["rounds"][0]["round_id"] != final["rounds"][1]["round_id"]


def test_historical_audit_uses_only_durable_transport():
    ss={}; chat=_chat(); ensure_store(chat)
    _append(chat, ss, 1); _append(chat, ss, 2)
    chat["conversation_record"]={"conversation_id":"conv119","session_id":"sess119","messages":[{"message_id":"m2","request_id":"req2","role":"user"}],"requests":[{"request_id":"req2","message_id":"m2"}],"rounds":[{"round_id":"conv119:req2:r2","request_id":"req2","message_id":"m2","round":2,"round_identity_contract":"V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1"}]}
    chat["request_records"]=chat["conversation_record"]["requests"][:]
    audit=authoritative_audit(chat, ss)
    assert audit["HISTORICAL_MESSAGE_COUNT"] == 2
    assert audit["HISTORICAL_REQUEST_COUNT"] == 2
    assert audit["HISTORICAL_ROUND_COUNT"] == 2
    assert audit["request_1_id"] == "req1"
    assert audit["request_2_id"] == "req2"
    assert audit["round_ids_unique"] is True
    assert audit["overall_authoritative_status"] == "PASS"


def test_missing_canonical_transport_is_not_proven_even_if_current_has_history():
    chat=_chat(); ensure_store(chat)
    chat["conversation_record"]["messages"]=[{"message_id":"m2","request_id":"req2","role":"user"}]
    chat["conversation_record"]["requests"]=[{"request_id":"req2","message_id":"m2"}]
    chat["conversation_record"]["rounds"]=[{"round_id":"conv119:req2:r2","request_id":"req2","message_id":"m2","round":2,"round_identity_contract":"V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1"}]
    audit=authoritative_audit(chat, None)
    assert audit["HISTORICAL_MESSAGE_COUNT"] == "NOT_PROVEN"
    assert audit["HISTORICAL_REQUEST_COUNT"] == "NOT_PROVEN"
    assert audit["HISTORICAL_ROUND_COUNT"] == "NOT_PROVEN"
    assert audit["overall_authoritative_status"] == "NOT_PROVEN"
