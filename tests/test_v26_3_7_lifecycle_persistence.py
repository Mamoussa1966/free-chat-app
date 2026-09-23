from conversation_store import ensure_store, commit_canonical_record, hydrate_canonical_record
from conversation_persistence_v26 import persist_identity
from conversation_v25_runtime import authoritative_audit

class SS(dict):
    pass

def _add(chat, ss, i):
    mid=f"m{i}"; rid=f"r{i}"; q=f"{chat['conversation_id']}:{rid}:r{i}"
    msg={"message_id":mid,"conversation_id":chat["conversation_id"],"session_id":chat["session_id"],"role":"user","request_id":rid,"created_at":f"2026-09-22T00:0{i}:00Z"}
    req={"request_id":rid,"message_id":mid,"conversation_id":chat["conversation_id"],"session_id":chat["session_id"],"state":"COMPLETED"}
    rnd={"round_id":q,"request_id":rid,"message_id":mid,"conversation_id":chat["conversation_id"],"session_id":chat["session_id"],"round":i,"status":"COMPLETED","round_identity_contract":"V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1"}
    persist_identity(chat, ss, message=msg, request=req, round_row=rnd)

def test_full_lifecycle_commits_every_identity():
    ss=SS(); chat={"conversation_id":"conv","session_id":"sess","conversation_record":{}}; ensure_store(chat)
    _add(chat,ss,1); _add(chat,ss,2)
    saved=ss["v26_3_canonical_conversation_store"]["conv"]["record"]
    assert len(saved["messages"]) == 2
    assert len(saved["requests"]) == 2
    assert len(saved["rounds"]) == 2

def test_rerun_hydrates_full_history_before_audit():
    ss=SS(); chat={"conversation_id":"conv","session_id":"sess","conversation_record":{}}; ensure_store(chat)
    _add(chat,ss,1); _add(chat,ss,2)
    fresh={"conversation_id":"conv","session_id":"sess","conversation_record":{},"request_records":[{"request_id":"r2","message_id":"m2"}],"messages":[],"round_ledger":[]}
    hydrate_canonical_record(fresh,ss)
    a=authoritative_audit(fresh)
    assert a["message_1_id"] == "m1" and a["message_2_id"] == "m2"
    assert a["request_1_id"] == "r1" and a["request_2_id"] == "r2"
    assert a["historical_round_count"] == 2
    assert a["overall_authoritative_status"] == "PASS"

def test_narrow_current_request_cannot_replace_canonical_history():
    ss=SS(); chat={"conversation_id":"conv","session_id":"sess","conversation_record":{}}; ensure_store(chat)
    _add(chat,ss,1); _add(chat,ss,2)
    fresh={"conversation_id":"conv","session_id":"sess","conversation_record":{},"request_records":[{"request_id":"r2","message_id":"m2"}],"messages":[],"round_ledger":[]}
    hydrate_canonical_record(fresh,ss)
    assert len(fresh["conversation_record"]["requests"]) == 2
    assert len(fresh["conversation_record"]["messages"]) == 2
    assert len(fresh["conversation_record"]["rounds"]) == 2
