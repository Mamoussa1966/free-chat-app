from conversation_persistence_v26 import persist_identity, hydrate_chat_identity
from conversation_v25_runtime import authoritative_audit

class SS(dict): pass

def _row(chat, ss, i):
    mid=f"m{i}"; rid=f"r{i}"; q=f"{chat['conversation_id']}:{rid}:r{i}"
    ts=f"2026-09-21T01:0{i}:00Z"
    msg={"message_id":mid,"conversation_id":chat["conversation_id"],"session_id":chat["session_id"],"role":"user","request_id":rid,"created_at":ts}
    req={"request_id":rid,"message_id":mid,"conversation_id":chat["conversation_id"],"session_id":chat["session_id"],"created_at":ts,"provider_execution_events":1,"cascade_attempts":1}
    rnd={"round_id":q.replace(":r1", f":r{i}"),"request_id":rid,"message_id":mid,"conversation_id":chat["conversation_id"],"session_id":chat["session_id"],"round":i,"round_identity_contract":"V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1","status":"COMPLETED"}
    persist_identity(chat,ss,message=msg,request=req,round_row=rnd)

def test_canonical_history_survives_hydration_and_audit_reads_both():
    ss=SS(); chat={"conversation_id":"conv","session_id":"sess","messages":[],"request_records":[],"round_ledger":[]}
    _row(chat,ss,1); _row(chat,ss,2)
    # simulate a narrower/current chat ledger after a rerun
    chat["request_records"] = [chat["v26_3_conversation_persistence"]["conv"]["requests"][-1]]
    fresh={"conversation_id":"conv","session_id":"sess","messages":[],"request_records":[],"round_ledger":[]}
    # transfer only canonical conversation state as the hydration payload
    fresh["v26_3_conversation_persistence"] = chat["v26_3_conversation_persistence"]
    hydrate_chat_identity(fresh, ss)
    audit=authoritative_audit(fresh,ss)
    assert audit["message_1_id"] == "m1"
    assert audit["message_2_id"] == "m2"
    assert audit["request_1_id"] == "r1"
    assert audit["request_2_id"] == "r2"
    assert audit["historical_persisted_request_count"] == 2
    assert audit["message_1_request_mapping"] is True
    assert audit["message_2_request_mapping"] is True
    assert audit["overall_authoritative_status"] == "PASS"

def test_missing_history_is_not_proven():
    chat={"conversation_id":"conv","session_id":"sess","v26_3_conversation_persistence":{"conv":{"messages":[],"requests":[],"rounds":[]}},"request_records":[]}
    audit=authoritative_audit(chat)
    assert audit["overall_authoritative_status"] == "NOT_PROVEN"
