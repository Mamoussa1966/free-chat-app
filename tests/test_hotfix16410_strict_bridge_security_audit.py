from copy import deepcopy

from production_platform import security_audit


PHASES = [
    ("SOURCE_EXECUTION", "SUCCESS"),
    ("WRITE", "RECORDED"),
    ("VALIDATE", "PASS"),
    ("COMMIT", "PASS"),
    ("BARRIER", "PASS"),
    ("TARGET_DISPATCH", "ACCEPTED"),
    ("TARGET_RESPONSE", "SUCCESS"),
    ("READ", "PASS"),
    ("MATCH", "PASS"),
]


def _runtime_record(rid: str, round_no: int, bridge_hash: str):
    return {
        "request_id": rid,
        "round_id": round_no,
        "canonical_round_id": f"conv:{rid}:r{round_no}",
        "bridge_id_hash": bridge_hash,
        "source_execution_proven": "PASS",
        "bridge_state_contains_value": "YES",
        "write_status": "PASS",
        "validate_status": "PASS",
        "commit_status": "PASS",
        "barrier_status": "PASS",
        "target_dispatch_status": "PASS",
        "target_response_status": "PASS",
        "read_status": "PASS",
        "schema_validation_status": "PASS",
        "match_status": "PASS",
        "user_prompt_contains_value": "NO",
        "gemini_input_prompt_contains_value": "NO",
        "runtime_http_payload_attested": "YES",
        "runtime_http_payload_contains_value": "NO",
        "runtime_http_payload_contains_bridge_key": "NO",
        "gemini_received_sanitized_representation_only": "PASS",
        "terminal_state": "COMMITTED",
        "bridge_state_terminal": "COMMITTED",
        "runtime_sequence_valid": "PASS",
        "application_owned": "PASS",
        "bridge_gate_status": "PASS",
        "bridge_trace_count": 2,
        "runtime_sequence": [
            {
                "seq": i,
                "phase": phase,
                "request_id": rid,
                "round_id": round_no,
                "status": status,
            }
            for i, (phase, status) in enumerate(PHASES, start=1)
        ],
    }


def _chat_with_strict_requests():
    r1 = "req-one"
    r2 = "req-two"
    return {
        "conversation_id": "conv",
        "messages": [],
        "conversation_record": {
            "messages": [],
            "requests": [
                {"request_id": r1, "message_id": "msg-one", "canonical_round_base": 1},
                {"request_id": r2, "message_id": "msg-two", "canonical_round_base": 2},
            ],
            "rounds": [
                {"round_id": f"conv:{r1}:r1", "request_id": r1, "message_id": "msg-one", "round_number": 1, "ordinal": 1},
                {"round_id": f"conv:{r2}:r2", "request_id": r2, "message_id": "msg-two", "round_number": 2, "ordinal": 2},
            ],
        },
        "request_records": [
            {"request_id": r1, "bridge_test_requested": True, "bridge_runtime_contract": "STRICT_LIVE", "results": []},
            {"request_id": r2, "bridge_test_requested": True, "bridge_runtime_contract": "STRICT_LIVE", "results": []},
        ],
        "bridge_runtime_evidence_store": {
            r1: _runtime_record(r1, 1, "hash-one"),
            r2: _runtime_record(r2, 2, "hash-two"),
        },
        "audit_events": [],
    }


def test_hotfix16410_security_audit_uses_application_owned_strict_bridge_store():
    chat = _chat_with_strict_requests()
    report = security_audit([chat])
    assert report["status"] == "PASS"
    assert report["checks"]["BRIDGE_VALUES_NOT_IN_USER_PROMPT"] is True
    assert report["checks"]["STRICT_LIVE_BRIDGE_EVIDENCE_AUTHORITATIVE_AND_COMPLETE"] is True


def test_hotfix16410_security_audit_fails_closed_when_strict_evidence_is_missing():
    chat = _chat_with_strict_requests()
    del chat["bridge_runtime_evidence_store"]["req-two"]
    report = security_audit([chat])
    assert report["status"] == "FAIL"
    assert report["checks"]["BRIDGE_VALUES_NOT_IN_USER_PROMPT"] is False
    assert report["checks"]["STRICT_LIVE_BRIDGE_EVIDENCE_AUTHORITATIVE_AND_COMPLETE"] is False


def test_hotfix16410_security_audit_rejects_bad_sequence_and_noncanonical_round_binding():
    chat = _chat_with_strict_requests()
    chat["bridge_runtime_evidence_store"]["req-one"]["runtime_sequence"][5]["phase"] = "READ"
    chat["bridge_runtime_evidence_store"]["req-two"]["canonical_round_id"] = "other-round"
    report = security_audit([chat])
    assert report["status"] == "FAIL"
    assert report["checks"]["STRICT_LIVE_BRIDGE_EVIDENCE_AUTHORITATIVE_AND_COMPLETE"] is False


def test_hotfix16410_security_audit_rejects_reused_bridge_identity_across_requests():
    chat = _chat_with_strict_requests()
    chat["bridge_runtime_evidence_store"]["req-two"]["bridge_id_hash"] = chat["bridge_runtime_evidence_store"]["req-one"]["bridge_id_hash"]
    report = security_audit([chat])
    assert report["status"] == "FAIL"
    assert report["checks"]["STRICT_LIVE_BRIDGE_EVIDENCE_AUTHORITATIVE_AND_COMPLETE"] is False


def test_hotfix16410_security_audit_does_not_accept_agent_result_audit_as_strict_proof():
    chat = _chat_with_strict_requests()
    chat["bridge_runtime_evidence_store"] = {}
    chat["request_records"][0]["results"] = [{
        "bridge_transaction_audit": {
            "BRIDGE_ID": "agent-result-id", "WRITE": "PASS", "VALIDATE": "PASS",
            "COMMIT": "PASS", "BARRIER": "PASS", "READ": "PASS",
            "SCHEMA_VALIDATION": "PASS", "MATCH": "PASS",
            "USER_PROMPT_CONTAINS_VALUE": "NO", "GEMINI_INPUT_PROMPT_CONTAINS_VALUE": "NO",
            "BRIDGE_STATE_CONTAINS_VALUE": "YES",
        }
    }]
    report = security_audit([chat])
    assert report["status"] == "FAIL"
    assert report["checks"]["STRICT_LIVE_BRIDGE_EVIDENCE_AUTHORITATIVE_AND_COMPLETE"] is False
