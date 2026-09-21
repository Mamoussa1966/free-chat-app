from conversation_store import ensure_store, canonical_upsert_message, canonical_upsert_request, canonical_upsert_round, assert_canonical_lifecycle_ready, hydrate_canonical_record
from conversation_v25_runtime import authoritative_audit

class SS(dict):
    pass

def add_request(chat, ss, n):
    mid=f"m{n}"; rid=f"r{n}"; oid=f"{chat['conversation_id']}:{rid}:r1"
    canonical_upsert_request(chat, {"request_id":rid,"message_id":mid,"conversation_id":"conv","session_id":"sess","state":"RUNNING"}, ss)
    canonical_upsert_message(chat, {"message_id":mid,"request_id":rid,"conversation_id":"conv","session_id":"sess","role":"user","created_at":f"2026-09-22T00:0{n}:00Z"}, ss)
    canonical_upsert_round(chat, {"round_id":oid,"request_id":rid,"message_id":mid,"conversation_id":"conv","session_id":"sess","round":1,"status":"STARTED"}, ss)
    assert_canonical_lifecycle_ready(chat, mid, rid, oid)

def test_two_requests_are_committed_before_dispatch_and_survive_hydration():
    ss=SS(); chat={"conversation_id":"conv","session_id":"sess","conversation_record":{}}; ensure_store(chat)
    add_request(chat, ss, 1); add_request(chat, ss, 2)
    saved=ss["v26_3_canonical_conversation_store"]["conv"]["record"]
    assert [x["request_id"] for x in saved["requests"]] == ["r1","r2"]
    assert [x["message_id"] for x in saved["messages"]] == ["m1","m2"]
    assert len(saved["rounds"]) == 2 and len({x["round_id"] for x in saved["rounds"]}) == 2
    fresh={"conversation_id":"conv","session_id":"sess","conversation_record":{}}
    hydrate_canonical_record(fresh, ss)
    assert len(fresh["conversation_record"]["messages"]) == 2
    assert len(fresh["conversation_record"]["requests"]) == 2
    assert len(fresh["conversation_record"]["rounds"]) == 2

def test_canonical_gate_rejects_missing_round():
    ss=SS(); chat={"conversation_id":"conv","session_id":"sess","conversation_record":{}}; ensure_store(chat)
    canonical_upsert_request(chat,{"request_id":"r1","message_id":"m1","conversation_id":"conv","session_id":"sess"},ss)
    canonical_upsert_message(chat,{"message_id":"m1","request_id":"r1","conversation_id":"conv","session_id":"sess","role":"user"},ss)
    try:
        assert_canonical_lifecycle_ready(chat,"m1","r1","conv:r1:r1")
    except RuntimeError as e:
        assert "CANONICAL_LIFECYCLE_NOT_READY" in str(e)
    else:
        raise AssertionError("missing canonical round was accepted")
