from conversation_v25_runtime import authoritative_audit
import main


def _bridge_audit(bid, req, source="DeepSeek / Seat 7", target="Gemini / Seat 2"):
    return {
        "BRIDGE_ID": bid,
        "WRITE": "PASS",
        "VALIDATE": "PASS",
        "COMMIT": "PASS",
        "BARRIER": "PASS",
        "READ": "PASS",
        "SCHEMA_VALIDATION": "PASS",
        "MATCH": "PASS",
        "SOURCE": source,
        "TARGET": target,
        "request_id": req,
        "BRIDGE_STATE_CONTAINS_VALUE": "YES",
        "USER_PROMPT_CONTAINS_VALUE": "NO",
        "GEMINI_INPUT_PROMPT_CONTAINS_VALUE": "NO",
    }


def _chat():
    return {
        "conversation_id": "conv-final",
        "session_id": "sess-final",
        "conversation_record": {
            "messages": [
                {"message_id": "m1", "request_id": "r1", "conversation_id": "conv-final", "session_id": "sess-final", "role": "user"},
                {"message_id": "m2", "request_id": "r2", "conversation_id": "conv-final", "session_id": "sess-final", "role": "user"},
            ],
            "requests": [
                {"request_id": "r1", "message_id": "m1", "conversation_id": "conv-final", "session_id": "sess-final", "canonical_round_base": 1,
                 "bridge_test_requested": True,
                 "results": [{"bridge_transaction_audit": _bridge_audit("BR-1", "r1"), "bridge_trace": [{"source_seat": 7, "target_seat": 2, "key": "BRIDGE_RESULT"}]}]},
                {"request_id": "r2", "message_id": "m2", "conversation_id": "conv-final", "session_id": "sess-final", "canonical_round_base": 2,
                 "bridge_test_requested": True,
                 "results": [{"bridge_transaction_audit": _bridge_audit("BR-2", "r2"), "bridge_trace": [{"source_seat": 7, "target_seat": 2, "key": "BRIDGE_RESULT"}]}]},
            ],
            "rounds": [
                {"round_id": "conv-final:r1:r1", "message_id": "m1", "request_id": "r1", "conversation_id": "conv-final", "session_id": "sess-final", "round": 1, "ordinal": 1, "record_type": "CANONICAL_ROUND_RECORD", "canonical_round_record_id": "conv-final:r1:r1", "canonical_identity_key": "conv-final:r1:r1", "round_identity_contract": "V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1"},
                {"round_id": "conv-final:r2:r2", "message_id": "m2", "request_id": "r2", "conversation_id": "conv-final", "session_id": "sess-final", "round": 2, "ordinal": 2, "record_type": "CANONICAL_ROUND_RECORD", "canonical_round_record_id": "conv-final:r2:r2", "canonical_identity_key": "conv-final:r2:r2", "round_identity_contract": "V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1"},
            ],
            "canonical_store_contract": "V26_3_CANONICAL_CONVERSATION_STORE",
            "canonical_store_committed": True,
        },
        "messages": [],
        "request_records": [],
        "result_ledger_v24": [],
        "provenance_ledger_v24": [],
        "bridge_ledger_v24": [],
        "message_synthesis_ledger_v25": [],
    }


def test_final_closure_uses_canonical_request_results_for_bridge_identity():
    audit = authoritative_audit(_chat())
    assert audit["bridge_evidence_source"] == "V26_3_CANONICAL_REQUEST_RECORD_RESULTS"
    assert audit["bridge_ids_message_1"] == ["BR-1"]
    assert audit["bridge_ids_message_2"] == ["BR-2"]
    assert audit["bridge_audit_record_count_message_1"] == 1
    assert audit["bridge_audit_record_count_message_2"] == 1
    assert audit["bridge_exactly_one_message_1"] is True
    assert audit["bridge_exactly_one_message_2"] is True
    assert audit["bridge_ids_distinct_message_1_vs_message_2"] is True
    assert audit["bridge_history_proven"] is True
    assert audit["conversation_runtime_audit"] == "PASS"


def test_final_closure_rejects_zero_target_trace():
    b = main.SharedContextBridge(request_id="r-final", round_no=1, application_owned_test=True)
    b.seed_application_state("BRIDGE_RESULT", "CANARY-FINAL", source="DeepSeek", source_seat=7)
    trace = b.transaction_trace()
    bridge_rows = [x for x in trace if x.get("key") == "BRIDGE_RESULT"]
    assert bridge_rows
    assert all(int(x.get("target_seat", 0) or 0) == 2 for x in bridge_rows)


def test_final_closure_rejects_duplicate_bridge_audits_even_with_same_id():
    chat = _chat()
    chat["conversation_record"]["requests"][0]["results"].append({
        "bridge_transaction_audit": _bridge_audit("BR-1", "r1"),
        "bridge_trace": [{"source_seat": 7, "target_seat": 2, "key": "BRIDGE_RESULT"}],
    })
    audit = authoritative_audit(chat)
    assert audit["bridge_audit_record_count_message_1"] == 2
    assert audit["bridge_exactly_one_message_1"] is False
    assert audit["bridge_history_proven"] is False
    assert audit["conversation_runtime_audit"] == "NOT_PROVEN"
