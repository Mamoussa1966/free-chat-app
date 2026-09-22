from conversation_store import ensure_store, canonical_upsert_message, canonical_upsert_request, canonical_upsert_round, commit_canonical_record, hydrate_canonical_record

class SS(dict):
    pass

def add(chat, ss, n):
    mid=f"m{n}"; rid=f"r{n}"; oid=f"{chat['conversation_id']}:{rid}:r1"
    canonical_upsert_message(chat, {"message_id":mid,"request_id":rid,"conversation_id":"conv","session_id":"sess","role":"user"}, ss)
    canonical_upsert_request(chat, {"request_id":rid,"message_id":mid,"conversation_id":"conv","session_id":"sess","state":"COMPLETED"}, ss)
    canonical_upsert_round(chat, {"round_id":oid,"request_id":rid,"message_id":mid,"conversation_id":"conv","session_id":"sess","round":1,"status":"COMPLETED"}, ss)

def test_commit_is_monotonic_against_narrow_current_record():
    ss=SS(); chat={"conversation_id":"conv","session_id":"sess","conversation_record":{}}; ensure_store(chat)
    add(chat,ss,1); add(chat,ss,2)
    assert len(ss["v26_3_canonical_conversation_store"]["conv"]["record"]["requests"]) == 2
    # Simulate a Streamlit rerun/runtime object that only has the current request.
    narrow={"conversation_id":"conv","session_id":"sess","conversation_record":{"messages":[{"message_id":"m2","request_id":"r2"}],"requests":[{"request_id":"r2","message_id":"m2"}],"rounds":[{"round_id":"conv:r2:r1","request_id":"r2","message_id":"m2"}]}}
    ensure_store(narrow)
    commit_canonical_record(narrow,ss)
    saved=ss["v26_3_canonical_conversation_store"]["conv"]["record"]
    assert {x["request_id"] for x in saved["requests"]} == {"r1","r2"}
    assert {x["message_id"] for x in saved["messages"]} == {"m1","m2"}
    assert len(saved["rounds"]) == 2

def test_hydration_restores_full_history_after_narrow_runtime_state():
    ss=SS(); source={"conversation_id":"conv","session_id":"sess","conversation_record":{}}; ensure_store(source)
    add(source,ss,1); add(source,ss,2)
    fresh={"conversation_id":"conv","session_id":"sess","conversation_record":{}}; ensure_store(fresh)
    hydrate_canonical_record(fresh,ss)
    assert len(fresh["conversation_record"]["messages"]) == 2
    assert len(fresh["conversation_record"]["requests"]) == 2
    assert len(fresh["conversation_record"]["rounds"]) == 2

def test_current_only_never_reduces_canonical_count():
    ss=SS(); chat={"conversation_id":"conv","session_id":"sess","conversation_record":{}}; ensure_store(chat)
    add(chat,ss,1); add(chat,ss,2)
    narrow={"conversation_id":"conv","session_id":"sess","conversation_record":{"messages":[{"message_id":"m2","request_id":"r2"}],"requests":[{"request_id":"r2","message_id":"m2"}],"rounds":[{"round_id":"conv:r2:r1","request_id":"r2","message_id":"m2"}]}}
    ensure_store(narrow); commit_canonical_record(narrow,ss)
    hydrated={"conversation_id":"conv","session_id":"sess","conversation_record":{}}; ensure_store(hydrated); hydrate_canonical_record(hydrated,ss)
    assert len(hydrated["conversation_record"]["requests"]) == 2
