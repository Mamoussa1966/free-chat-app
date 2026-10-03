from production_platform import conversation_persistence_audit, session_integrity_audit, build_v23_platform_audit

def _chat():
    return {
        "id": "session-1",
        "conversation_id": "conv-test",
        "session_id": "sess-test",
        "conversation_record": {
            "conversation_id": "conv-test", "session_id": "sess-test",
            "canonical_store_contract": "V26_3_CANONICAL_CONVERSATION_STORE",
            "canonical_store_committed": True,
            "messages": [{"message_id":"m1","conversation_id":"conv-test","session_id":"sess-test","role":"user","request_id":"r1"}],
            "requests": [{"request_id":"r1","conversation_id":"conv-test","session_id":"sess-test","message_id":"m1"}],
            "rounds": [{"round_id":"conv-test:r1:r1","conversation_id":"conv-test","session_id":"sess-test","message_id":"m1","request_id":"r1","round":1,"round_identity_contract":"V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1","status":"COMPLETED"}]
        },
        "messages": [{"role":"user","content":"hello","request_id":"r1"}],
        "request_records": [{
            "request_id":"r1", "rounds_executed":1,
            "results":[{"status":"SUCCESS","attempt_summaries":[{"attempt":1}],"bridge_transaction_audit":{"BRIDGE_ID":"b1"}}],
            "request_metrics":{"unique_request_ids":1}, "synthesis":{"status":"READY"}
        }],
        "history_identity_ledger":[["r1",1,"deepseek"]]
    }

def test_persistence_audit_passes_safe_runtime_record():
    r=conversation_persistence_audit(_chat(), "r1")
    assert r["status"] == "PASS"

def test_session_integrity_detects_duplicates():
    c=_chat(); c["request_records"].append(dict(c["request_records"][0])); c["history_identity_ledger"].append(["r1",1,"deepseek"])
    r=session_integrity_audit(c,"r1")
    assert r["status"] == "FAIL"
    assert r["duplicate_requests"] == 1
    assert r["duplicate_seat_round_executions"] == 1

def test_full_v23_audit_is_not_not_run():
    c=_chat(); sec={"status":"PASS"}; health=[{"status":"READY"}]; reg={"gate":"PASS"}; ctx={"chars":123,"messages_included":2,"messages_dropped":0,"digest":"abc"}
    r=build_v23_platform_audit(c,"r1",ctx,health,sec,reg)
    assert r["status"] == "PASS"
    assert r["conversation_persistence"]["status"] == "PASS"
    assert r["session_integrity"]["status"] == "PASS"
