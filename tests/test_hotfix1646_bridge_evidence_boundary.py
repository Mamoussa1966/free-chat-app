import main
from conversation_v25_runtime import authoritative_audit


def test_hotfix1646_runtime_record_has_complete_application_owned_contract():
    bridge = main.SharedContextBridge(request_id="req-1646", round_no=1, application_owned_test=True)
    required = {
        "request_id", "round_id", "bridge_id_hash", "source_execution_proven",
        "write_status", "validate_status", "commit_status", "barrier_status",
        "target_dispatch_status", "target_response_status", "read_status",
        "schema_validation_status", "match_status", "user_prompt_contains_value",
        "gemini_input_prompt_contains_value", "runtime_http_payload_attested",
        "runtime_http_payload_contains_value", "runtime_http_payload_contains_bridge_key",
        "gemini_received_sanitized_representation_only", "terminal_state",
    }
    record = bridge.runtime_evidence_record()
    assert required <= set(record)
    assert record["request_id"] == "req-1646"
    assert record["bridge_id"] == "[REDACTED]"


def test_hotfix1646_final_audit_reads_runtime_store_directly_and_never_provider_output():
    chat = {
        "conversation_id": "c",
        "session_id": "s",
        "conversation_record": {
            "messages": [
                {"message_id": "m1", "request_id": "r1", "role": "user"},
                {"message_id": "m2", "request_id": "r2", "role": "user"},
            ],
            "requests": [
                {"request_id": "r1", "message_id": "m1", "canonical_round_base": 1,
                 "results": [{"bridge_transaction_audit": {"BRIDGE_ID": "PROVIDER-ONLY"}}]},
                {"request_id": "r2", "message_id": "m2", "canonical_round_base": 2,
                 "results": [{"bridge_transaction_audit": {"BRIDGE_ID": "PROVIDER-ONLY-2"}}]},
            ],
            "rounds": [
                {"round_id": "c:r1:r1", "message_id": "m1", "request_id": "r1", "round": 1, "ordinal": 1},
                {"round_id": "c:r2:r2", "message_id": "m2", "request_id": "r2", "round": 2, "ordinal": 2},
            ],
        },
        "request_records": [],
        "bridge_runtime_evidence_store": {
            "r1": {"bridge_id_hash": "h1", "write_status": "PASS", "terminal_state": "COMMITTED"},
            "r2": {"bridge_id_hash": "h2", "write_status": "PASS", "terminal_state": "COMMITTED"},
        },
    }
    session = {"v26_3_canonical_conversation_store": {
        "c": {"record": dict(chat["conversation_record"]), "history_hash": "h", "revision": 1}
    }}
    audit = authoritative_audit(chat, session)
    assert audit["bridge_evidence_source"] == "APPLICATION_OWNED_BRIDGE_RUNTIME_EVIDENCE_STORE"
    assert audit["bridge_lifecycle_message_1"]["bridge_id_hash"] == "h1"
    assert audit["bridge_lifecycle_message_2"]["bridge_id_hash"] == "h2"
