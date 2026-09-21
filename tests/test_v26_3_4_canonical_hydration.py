from conversation_persistence_v26 import snapshot_chat_identity
from conversation_v25_runtime import authoritative_audit

class SS(dict):
    pass

def test_v2634_hydrates_history_from_canonical_chat_messages_and_real_rounds():
    ss=SS()
    chat={
        "conversation_id":"conv", "session_id":"sess",
        "messages":[
            {"id":"m1","role":"user","request_id":"r1","created_at":"2026-09-21T00:00:00Z"},
            {"id":"m2","role":"user","request_id":"r2","created_at":"2026-09-21T00:01:00Z"},
        ],
        "message_ledger":[],
        "request_records":[{"request_id":"r2","message_id":"m2"}],
        "request_ledger_v24":[
            {"request_id":"r1","message_id":"m1","conversation_id":"conv","session_id":"sess","status":"COMPLETED"},
            {"request_id":"r2","message_id":"m2","conversation_id":"conv","session_id":"sess","status":"COMPLETED"},
        ],
        "round_ledger":[
            {"round_id":"conv:r1:r1","request_id":"r1","message_id":"m1","conversation_id":"conv","session_id":"sess","round":1,"status":"COMPLETED"},
            {"round_id":"conv:r2:r1","request_id":"r2","message_id":"m2","conversation_id":"conv","session_id":"sess","round":1,"status":"COMPLETED"},
        ],
    }
    snapshot_chat_identity(chat,ss)
    # Simulate hydration with only current request_records retained. Canonical object survives.
    fresh={"conversation_id":"conv","session_id":"sess","conversation_record":chat["conversation_record"],
           "messages":chat["messages"],"request_records":[{"request_id":"r2","message_id":"m2"}],"round_ledger":[]}
    a=authoritative_audit(fresh)
    assert a["message_1_id"] == "m1"
    assert a["message_2_id"] == "m2"
    assert a["request_1_id"] == "r1"
    assert a["request_2_id"] == "r2"
    assert a["message_1_request_mapping"] is True
    assert a["message_2_request_mapping"] is True
    assert a["overall_authoritative_status"] == "PASS"

def test_v2634_does_not_mint_round_ids():
    ss=SS()
    chat={"conversation_id":"conv","session_id":"sess","messages":[{"id":"m1","role":"user","request_id":"r1"}],"request_records":[{"request_id":"r1","message_id":"m1"}],"request_ledger_v24":[],"round_ledger":[]}
    snapshot_chat_identity(chat,ss)
    bucket=chat["conversation_record"]["v26_3_conversation_persistence"]["conv"]
    assert bucket["rounds"] == []
