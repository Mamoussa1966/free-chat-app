from conversation_persistence_v26 import persist_identity, hydrate_chat_identity, persistence_audit
from conversation_v25_runtime import authoritative_audit

class SS(dict):
    pass

def _add(chat, ss, i):
    mid=f"m{i}"; rid=f"r{i}"; q=f"{chat['conversation_id']}:{rid}:r{i}"
    msg={"message_id":mid,"conversation_id":chat["conversation_id"],"session_id":chat["session_id"],"role":"user","request_id":rid,"created_at":f"2026-09-21T00:0{i}:00Z"}
    req={"request_id":rid,"message_id":mid,"conversation_id":chat["conversation_id"],"session_id":chat["session_id"]}
    rnd={"round_id":q,"request_id":rid,"message_id":mid,"conversation_id":chat["conversation_id"],"session_id":chat["session_id"],"round":i,"round_identity_contract":"V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1"}
    persist_identity(chat, ss, message=msg, request=req, round_row=rnd)

def test_canonical_record_survives_reconstruction_and_narrow_current_ledgers():
    ss=SS(); chat={"conversation_id":"conv","session_id":"sess","messages":[],"request_records":[],"round_ledger":[]}
    _add(chat,ss,1); _add(chat,ss,2)
    assert len(chat["conversation_record"]["v26_3_conversation_persistence"]["conv"]["messages"]) == 2
    # Simulate Streamlit rerun: reconstruct only the canonical conversation object.
    fresh={"conversation_id":"conv","session_id":"sess","conversation_record":chat["conversation_record"],"request_records":[{"request_id":"r2","message_id":"m2"}],"messages":[],"round_ledger":[]}
    hydrate_chat_identity(fresh, ss)
    audit=authoritative_audit(fresh)
    assert audit["message_1_id"] == "m1"
    assert audit["message_2_id"] == "m2"
    assert audit["request_1_id"] == "r1"
    assert audit["request_2_id"] == "r2"
    assert audit["historical_persisted_request_count"] == 2
    assert audit["message_1_request_mapping"] is True
    assert audit["message_2_request_mapping"] is True
    assert audit["overall_authoritative_status"] == "PASS"

def test_session_state_cannot_rescue_missing_canonical_history():
    ss=SS(); ss["v26_3_conversation_persistence"]={"conv":{"messages":[{"message_id":"m1","request_id":"r1"}],"requests":[{"request_id":"r1","message_id":"m1"}],"rounds":[]}}
    chat={"conversation_id":"conv","session_id":"sess","conversation_record":{},"request_records":[]}
    audit=authoritative_audit(chat)
    assert audit["overall_authoritative_status"] == "NOT_PROVEN"
