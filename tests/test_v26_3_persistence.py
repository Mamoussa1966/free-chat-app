from conversation_persistence_v26 import ensure_persistence_store, persist_identity, hydrate_chat_identity, persistence_audit
from conversation_v25_runtime import authoritative_audit

class SS(dict):
    pass

def _seed():
    ss = SS(); ensure_persistence_store(ss)
    chat = {"conversation_id":"conv-A", "session_id":"sess-A", "message_ledger":[], "request_records":[], "round_ledger":[], "conversation_record":{}}
    for i in (1,2):
        mid=f"m{i}"; rid=f"r{i}"; round_id=f"conv-A:{rid}:r1"
        msg={"message_id":mid,"conversation_id":"conv-A","session_id":"sess-A","role":"user","request_id":rid,"created_at":f"2026-01-01T00:0{i}:00Z"}
        req={"request_id":rid,"message_id":mid,"conversation_id":"conv-A","session_id":"sess-A","created_at":msg["created_at"]}
        rnd={"round_id":round_id,"message_id":mid,"request_id":rid,"conversation_id":"conv-A","session_id":"sess-A","round":1}
        persist_identity(chat, ss, message=msg, request=req, round_row=rnd)
    return chat, ss

def test_two_message_request_round_chain_survives_canonical_hydration():
    chat, ss = _seed()
    # Simulate a Streamlit rerun: the canonical ConversationRecord is retained;
    # transient current ledgers are reconstructed from it.
    fresh={"conversation_id":"conv-A","session_id":"sess-A","message_ledger":[],"request_records":[],"round_ledger":[],"conversation_record":chat["conversation_record"]}
    hydrate_chat_identity(fresh, ss)
    assert {x["message_id"] for x in fresh["message_ledger"]} == {"m1","m2"}
    assert {x["request_id"] for x in fresh["request_records"]} == {"r1","r2"}
    assert {x["round_id"] for x in fresh["round_ledger"]} == {"conv-A:r1:r1","conv-A:r2:r1"}
    assert persistence_audit(fresh, ss)["persisted_request_count"] == 2

def test_authoritative_audit_uses_full_historical_conversation_record():
    chat, ss = _seed()
    # Narrow current ledger intentionally to one request; authoritative history
    # must remain two records and must report the narrowing conflict.
    chat["request_records"] = [chat["conversation_record"]["requests"][-1]]
    audit = authoritative_audit(chat)
    assert audit["message_1_id"] == "m1"
    assert audit["message_2_id"] == "m2"
    assert audit["request_1_id"] == "r1"
    assert audit["request_2_id"] == "r2"
    assert audit["HISTORICAL_MESSAGE_COUNT"] == 2
    assert audit["HISTORICAL_REQUEST_COUNT"] == 2
    assert audit["HISTORICAL_ROUND_COUNT"] == 2
    assert audit["historical_narrowing_conflict"] is True
    assert audit["agent_prose_used_as_identity"] == "NO"

def test_identity_conflict_does_not_overwrite_persistence():
    ss=SS(); ensure_persistence_store(ss)
    chat={"conversation_id":"conv-B","session_id":"sess-B","message_ledger":[],"request_records":[],"round_ledger":[],"conversation_record":{}}
    persist_identity(chat, ss, message={"message_id":"m1","request_id":"r1"})
    persist_identity(chat, ss, message={"message_id":"m1","request_id":"r2"})
    rows=ss["v26_3_conversation_persistence"]["conv-B"]["messages"]
    assert len(rows)==1
    assert rows[0]["request_id"]=="r1"
    assert rows[0]["identity_conflict"] is True
