from conversation_runtime import ensure_conversation_state, register_message, begin_round, finish_round, attach_request_identity, append_provenance, conversation_audit


def test_conversation_and_session_identity_are_stable():
    chat = {"id": "conv1", "messages": [], "request_records": []}
    ensure_conversation_state(chat)
    cid, sid = chat["conversation_id"], chat["session_id"]
    register_message(chat, {"id": "m1", "role": "user", "content": "hello", "request_id": "r1"})
    register_message(chat, {"id": "m2", "role": "assistant", "content": "ok", "request_id": "r1"})
    assert chat["conversation_id"] == cid
    assert chat["session_id"] == sid
    assert chat["message_ledger"][-1]["conversation_id"] == cid


def test_round_and_request_identity_are_distinct_across_rounds():
    chat = {"id": "conv2", "messages": [], "request_records": []}
    ensure_conversation_state(chat)
    rec = {"request_id": "r1"}
    attach_request_identity(rec, chat, "m1", "r1")
    a = begin_round(chat, "m1", "r1", 1)
    finish_round(chat, a, "COMPLETED", 2)
    b = begin_round(chat, "m2", "r2", 1)
    assert a != b
    assert rec["conversation_id"] == chat["conversation_id"]
    assert rec["session_id"] == chat["session_id"]


def test_provenance_is_safe_and_application_owned():
    chat = {"id": "conv3", "messages": [], "request_records": []}
    ensure_conversation_state(chat)
    append_provenance(chat, {"conversation_id": chat["conversation_id"], "session_id": chat["session_id"], "message_id": "m", "round_id": "r", "request_id": "req", "provider": "Gemini", "seat": "2", "model": "gemini-3.6-flash", "attempt": 1, "status": "SUCCESS", "classification": "", "cascade_action": "NONE"})
    assert conversation_audit(chat)["status"] == "PASS"
    assert "api_key" not in str(chat["provenance_ledger"]).lower()


def test_runtime_does_not_claim_bridge_ownership():
    chat = {"id": "conv4", "messages": [], "request_records": []}
    ensure_conversation_state(chat)
    append_provenance(chat, {"conversation_id": chat["conversation_id"], "session_id": chat["session_id"], "message_id": "m", "round_id": "r", "request_id": "req", "provider": "DeepSeek", "seat": "7", "model": "deepseek-flash", "attempt": 1, "status": "SUCCESS"})
    assert conversation_audit(chat)["checks"]["NO_BRIDGE_OWNERSHIP"]
