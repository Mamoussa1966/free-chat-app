"""HOTFIX164.19 regression: inspect existing Requests without modifying or rerunning them."""
from __future__ import annotations

import copy

from production_platform import conversation_persistence_audit, read_only_existing_records_audit
from v23_final_closure_audit import build_v23_final_closure_audit


def _chat_with_two_completed_requests_and_unproven_third():
    requests = []
    messages = []
    rounds = []
    direct = []
    for number in range(1, 4):
        rid = f"request-{number}"
        mid = f"message-{number}"
        messages.append({
            "message_id": mid, "conversation_id": "conversation-x", "session_id": "session-x",
            "role": "user", "request_id": rid,
        })
        requests.append({
            "request_id": rid, "message_id": mid, "conversation_id": "conversation-x",
            "session_id": "session-x", "state": "COMPLETED" if number < 3 else "CREATED",
        })
        rounds.append({
            "round_id": f"conversation-x:{rid}:r{number}", "request_id": rid, "message_id": mid,
            "conversation_id": "conversation-x", "session_id": "session-x",
            "round": number, "round_number": number, "ordinal": number,
        })
        if number < 3:
            direct.append({
                "request_id": rid,
                "results": [{
                    "request_id": rid, "status": "SUCCESS", "executed_model": "model-free-1",
                    "attempt_summaries": [{"attempt": 1, "status": "SUCCESS"}],
                    "runtime_execution_events": [{
                        "execution_started": True, "request_id": rid,
                        "model": "model-free-1", "status": "SUCCESS",
                    }],
                }],
                "synthesis": {"status": "READY"},
                "request_metrics": {"provider_execution_events": 1},
            })
        else:
            # This row only proves the Request was created; it intentionally has no
            # execution/result artifacts and must never be repaired by the audit.
            direct.append({"request_id": rid, "state": "CREATED"})
    return {
        "id": "session-x", "conversation_id": "conversation-x", "session_id": "session-x",
        "messages": copy.deepcopy(messages), "request_records": direct,
        "conversation_record": {
            "canonical_store_contract": "V26_3_CANONICAL_CONVERSATION_STORE",
            "conversation_id": "conversation-x", "session_id": "session-x",
            "messages": messages, "requests": requests, "rounds": rounds,
        },
        "bridge_runtime_evidence_store": {}, "audit_events": [],
    }


def test_hotfix16419_read_only_audit_keeps_third_request_unproven_and_does_not_mutate_state():
    chat = _chat_with_two_completed_requests_and_unproven_third()
    before = copy.deepcopy(chat)

    report = read_only_existing_records_audit(chat)

    assert report["status"] == "NOT_PROVEN"
    assert report["mode"] == "READ_ONLY"
    assert report["read_only"] is True
    assert report["canonical_counts"] == {
        "canonical_message_count": 3,
        "canonical_request_count": 3,
        "canonical_round_count": 3,
    }
    assert report["canonical_counter_consistent"] is True
    assert report["read_side_effects"] == "NONE_OBSERVED"
    assert report["live_state_unchanged"] is True
    assert report["provider_execution"] == report["cascade_execution"] == 0
    assert report["new_requests"] == report["new_rounds"] == report["new_bridges"] == 0
    by_id = {row["request_id"]: row for row in report["requests"]}
    assert by_id["request-1"]["status"] == "PASS"
    assert by_id["request-2"]["status"] == "PASS"
    assert by_id["request-3"]["status"] == "NOT_PROVEN"
    assert by_id["request-3"]["request_execution_status"] == "NOT_PROVEN"
    assert by_id["request-3"]["missing_required_artifacts"] == [
        "AUTHORITATIVE_METRICS", "CASCADE_SUMMARIES", "EXECUTED_MODELS", "FINAL_RESULT", "SEAT_RESULTS"
    ]
    assert chat == before


def test_hotfix16419_counter_semantics_are_separate_from_request_completeness():
    chat = _chat_with_two_completed_requests_and_unproven_third()
    audit = conversation_persistence_audit(chat, "request-3")

    assert audit["status"] == "FAIL"
    assert audit["counter_semantics_consistent"] is True
    assert audit["canonical_message_count"] == audit["canonical_request_count"] == audit["canonical_round_count"] == 3
    assert audit["audited_request_id"] == "request-3"
    assert "MISSING_REQUIRED_ARTIFACT:SEAT_RESULTS" in audit["failure_reasons"]
    assert "MISSING_REQUIRED_ARTIFACT:FINAL_RESULT" in audit["failure_reasons"]


def test_hotfix16419_final_closure_cannot_pass_when_platform_audit_fails_even_if_counts_match():
    chat = _chat_with_two_completed_requests_and_unproven_third()
    platform = {
        "status": "FAIL",
        "conversation_persistence": {
            "status": "FAIL", "persisted_message_count": 3,
            "persisted_request_count": 3, "persisted_round_count": 3,
            "counter_semantics_consistent": True,
        },
    }
    security = {"status": "PASS", "checks": {"NO_CREDENTIALS_IN_CHAT_STATE": True}}

    report = build_v23_final_closure_audit(chat, security, platform, [])

    assert report["canonical_lifecycle"]["counter_semantics_consistent"] is True
    assert report["status"] == "FAIL"
    assert "PLATFORM_AUDIT_NOT_PASS" in report["closure_blockers"]
    assert "CONVERSATION_PERSISTENCE_NOT_PASS" in report["closure_blockers"]


def test_hotfix16419_explicit_cross_request_execution_event_is_fail_not_not_proven():
    chat = _chat_with_two_completed_requests_and_unproven_third()
    chat["request_records"][0]["results"][0]["runtime_execution_events"][0]["request_id"] = "request-2"

    report = read_only_existing_records_audit(chat)
    row = next(row for row in report["requests"] if row["request_id"] == "request-1")

    assert report["status"] == "FAIL"
    assert row["execution_identity_status"] == "FAIL"
    assert row["status"] == "FAIL"
    assert "READ_ONLY_STATE_CHANGED_OR_COULD_NOT_BE_VERIFIED" not in report["blockers"]
