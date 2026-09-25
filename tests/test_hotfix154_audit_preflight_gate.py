from conversation_store import canonical_audit_preflight
from production_platform import conversation_persistence_audit


def _chat():
    return {
        "id": "sess-154", "conversation_id": "conv-154", "session_id": "sess-154",
        "messages": [{"role": "user", "content": "ui"}] * 6,
        "conversation_record": {
            "conversation_id": "conv-154", "session_id": "sess-154",
            "messages": [
                {"message_id": "m1", "role": "user", "request_id": "req1"},
                {"message_id": "m2", "role": "user", "request_id": "req2"},
            ],
            "requests": [
                {"request_id": "req1", "message_id": "m1"},
                {"request_id": "req2", "message_id": "m2"},
            ],
            "rounds": [
                {"round_id": "conv-154:r1", "request_id": "req1", "message_id": "m1", "round": 1},
                {"round_id": "conv-154:r2", "request_id": "req2", "message_id": "m2", "round": 2},
            ],
        },
        "request_records": [
            {"request_id": "req2", "rounds_executed": 1, "results": [{"status": "SUCCESS", "attempt_summaries": [{"attempt": 1}]}], "request_metrics": {"unique_request_ids": 1}, "synthesis": {"status": "READY"}}
        ],
    }


def test_persistence_audit_invokes_canonical_preflight_and_exposes_gate():
    c = _chat()
    r = conversation_persistence_audit(c, "req2")
    assert r["canonical_audit_preflight_invoked"] is True
    assert r["canonical_audit_preflight_status"] == "PASS"
    assert r["canonical_message_count"] == 2
    assert r["canonical_request_count"] == 2
    assert r["canonical_round_count"] == 2
    assert r["ui_projection_message_count"] == 6
    assert r["ui_projection_message_count_authoritative"] is False


def test_missing_canonical_evidence_is_fail_closed_not_pass():
    c = _chat()
    c.pop("conversation_record")
    r = canonical_audit_preflight(c, None)
    assert r["status"] == "NOT_PROVEN"
    assert r["canonical_store_loaded"] is True


def test_persistence_path_exposes_nonpassing_preflight_when_canonical_evidence_is_missing():
    c = _chat()
    c.pop("conversation_record")
    r = conversation_persistence_audit(c, "req2")
    assert r["canonical_audit_preflight_invoked"] is True
    assert r["canonical_audit_preflight_status"] == "NOT_PROVEN"
    assert r["status"] == "FAIL"


def test_empty_continuation_evidence_remains_not_proven():
    from production_platform import build_v23_platform_audit
    c = _chat()
    report = build_v23_platform_audit(c, "req2", {"chars": 1, "digest": "x"}, [{"status": "READY"}], {"status": "PASS"}, {"gate": "PASS"})
    gate = report["continuation_runtime_gate"]
    assert gate["audit"] == {}
    assert gate["status"] == "NOT_PROVEN"
