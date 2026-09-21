import copy
from conversation_persistence_v26 import ensure_persistence_store, persist_identity, hydrate_chat_identity, persistence_audit

class SS(dict):
    pass

def test_two_message_request_round_chain_survives_hydration():
    ss = SS(); ensure_persistence_store(ss)
    chat = {"conversation_id":"conv-A", "session_id":"sess-A", "message_ledger":[], "request_records":[], "round_ledger":[]}
    for i in (1,2):
        mid=f"m{i}"; rid=f"r{i}"; round_id=f"conv-A:{rid}:r1"
        msg={"message_id":mid,"conversation_id":"conv-A","session_id":"sess-A","role":"user","request_id":rid,"created_at":f"2026-01-01T00:0{i}:00Z"}
        req={"request_id":rid,"message_id":mid,"conversation_id":"conv-A","session_id":"sess-A","created_at":msg["created_at"]}
        rnd={"round_id":round_id,"message_id":mid,"request_id":rid,"conversation_id":"conv-A","session_id":"sess-A","round":1}
        persist_identity(chat, ss, message=msg, request=req, round_row=rnd)
    fresh={"conversation_id":"conv-A","session_id":"sess-A","message_ledger":[],"request_records":[],"round_ledger":[]}
    hydrate_chat_identity(fresh, ss)
    assert {x["message_id"] for x in fresh["message_ledger"]} == {"m1","m2"}
    assert {x["request_id"] for x in fresh["request_records"]} == {"r1","r2"}
    assert {x["round_id"] for x in fresh["round_ledger"]} == {"conv-A:r1:r1","conv-A:r2:r1"}
    assert persistence_audit(fresh, ss)["persisted_request_count"] == 2

def test_identity_conflict_does_not_overwrite_persistence():
    ss=SS(); ensure_persistence_store(ss)
    chat={"conversation_id":"conv-B","session_id":"sess-B","message_ledger":[],"request_records":[],"round_ledger":[]}
    persist_identity(chat, ss, message={"message_id":"m1","request_id":"r1"})
    persist_identity(chat, ss, message={"message_id":"m1","request_id":"r2"})
    rows=ss["v26_3_conversation_persistence"]["conv-B"]["messages"]
    assert len(rows)==1
    assert rows[0]["request_id"]=="r1"
    assert rows[0]["identity_conflict"] is True
