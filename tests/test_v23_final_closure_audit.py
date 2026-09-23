from v23_final_closure_audit import build_v23_final_closure_audit, semantic_execution_counters


def canonical_chat():
    return {
        "id": "sess-x",
        "messages": [
            {"message_id": "m1", "role": "user", "content": "one"},
            {"message_id": "m2", "role": "user", "content": "two"},
            {"role": "assistant", "content": "artifact"},
            {"role": "system", "content": "artifact"},
        ],
        "conversation_record": {
            "messages": [
                {"message_id": "m1", "role": "user"},
                {"message_id": "m2", "role": "user"},
                {"message_id": "a1", "role": "assistant"},
            ],
            "requests": [{"request_id": "r1"}, {"request_id": "r2"}],
            "rounds": [{"round_id": "r1:r1"}, {"round_id": "r2:r2"}],
        },
        "request_records": [
            {"request_id": "r1", "results": [{"runtime_execution_events": [{"execution_started": True, "request_id": "r1"}]}]},
            {"request_id": "r2", "results": [{"runtime_execution_events": [
                {"execution_started": True, "request_id": "r2"},
                {"execution_started": True, "request_id": "r2"},
            ]}]},
        ],
    }


def test_execution_status_semantics_are_not_mixed():
    c = canonical_chat()
    counters = semantic_execution_counters(c, [{"status": "SUCCESS"}, {"status": "SUCCESS"}])
    assert counters["request_created"] == 2
    assert counters["request_created_source"] == "CANONICAL_REQUEST_RECORDS"
    assert counters["execution_started"] == 3
    assert counters["not_executed"] == 0
    assert counters["ui_result_rows"] == 2
    assert counters["ui_message_count"] == 4
    assert counters["ui_message_count_authoritative"] is False


def test_final_closure_fails_only_when_security_or_canonical_evidence_fails():
    c = canonical_chat()
    security = {"status": "PASS", "checks": {"A": True, "B": True}}
    platform = {"status": "PASS", "conversation_persistence": {
        "persisted_message_count": 2,
        "persisted_request_count": 2,
        "persisted_round_count": 2,
        "counter_semantics_consistent": True,
    }}
    report = build_v23_final_closure_audit(c, security, platform, [])
    assert report["status"] == "PASS"
    assert report["canonical_lifecycle"]["HOTFIX130_SEMANTICS_PRESERVED"] is True
    assert report["ui_projection"]["message_count_authoritative"] is False


def test_security_failure_is_explained_and_not_converted_to_pass():
    c = canonical_chat()
    security = {"status": "FAIL", "checks": {"NO_CREDENTIALS_IN_CHAT_STATE": True, "PROSE_ISOLATION_AUTHORITATIVE_GATE": False}}
    platform = {"conversation_persistence": {
        "persisted_message_count": 2,
        "persisted_request_count": 2,
        "persisted_round_count": 2,
        "counter_semantics_consistent": True,
    }}
    report = build_v23_final_closure_audit(c, security, platform, [])
    assert report["status"] == "FAIL"
    assert report["security"]["failure_reasons"] == ["PROSE_ISOLATION_AUTHORITATIVE_GATE"]
