from __future__ import annotations

import copy

from conversation_store import (
    _restore_saved_identity_order,
    reconcile_canonical_round_completion_statuses,
)


def _record() -> dict:
    conversation_id = "conversation-12345678"
    session_id = "session-12345678"
    request_id = "request-12345678"
    message_id = "message-12345678"
    round_id = f"{conversation_id}:{request_id}:r1"
    results = [
        {
            "request_id": request_id,
            "round": "1",
            "seat": "gemini",
            "status": "SUCCESS",
            "result_key": f"{request_id}:1:gemini",
            "executed_model": "gemini-3.6-flash",
        },
        {
            "request_id": request_id,
            "round": "1",
            "seat": "cloudflare_workers_ai",
            "status": "SUCCESS",
            "result_key": f"{request_id}:1:cloudflare_workers_ai",
            "executed_model": "@cf/zai-org/glm-4.7-flash",
        },
    ]
    return {
        "conversation_id": conversation_id,
        "session_id": session_id,
        "messages": [
            {
                "message_id": message_id,
                "conversation_id": conversation_id,
                "session_id": session_id,
                "role": "user",
                "request_id": request_id,
                "created_at": "2026-11-09T10:00:00Z",
            }
        ],
        "requests": [
            {
                "request_id": request_id,
                "message_id": message_id,
                "conversation_id": conversation_id,
                "session_id": session_id,
                "state": "COMPLETED",
                "results": results,
                "created_at": "2026-11-09T10:00:01Z",
            }
        ],
        "rounds": [
            {
                "round_id": round_id,
                "canonical_round_record_id": round_id,
                "canonical_identity_key": round_id,
                "record_type": "CANONICAL_ROUND_RECORD",
                "round_identity_contract": "V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1",
                "conversation_id": conversation_id,
                "session_id": session_id,
                "message_id": message_id,
                "request_id": request_id,
                "round": 1,
                "ordinal": 1,
                "status": "STARTED",
                "finished_at": "2026-11-09T10:00:05Z",
                "result_count": 2,
                "created_at": "2026-11-09T10:00:02Z",
            }
        ],
    }


def test_saved_identity_merge_does_not_roll_completed_round_back_to_started():
    current = [
        {
            "round_id": "round-1",
            "status": "COMPLETED",
            "result_count": 2,
            "finished_at": "2026-11-09T10:00:05Z",
        }
    ]
    saved = [
        {
            "round_id": "round-1",
            "status": "STARTED",
            "created_at": "2026-11-09T10:00:02Z",
        }
    ]

    merged = _restore_saved_identity_order(current, saved, "round_id")

    assert len(merged) == 1
    assert merged[0]["status"] == "COMPLETED"
    assert merged[0]["result_count"] == 2
    assert merged[0]["finished_at"] == "2026-11-09T10:00:05Z"
    assert merged[0]["created_at"] == "2026-11-09T10:00:02Z"


def test_saved_identity_merge_preserves_current_immutable_binding_and_marks_conflict():
    current = [{"round_id": "round-1", "request_id": "request-current"}]
    saved = [{"round_id": "round-1", "request_id": "request-saved", "status": "STARTED"}]

    merged = _restore_saved_identity_order(current, saved, "round_id")

    assert merged[0]["request_id"] == "request-current"
    assert merged[0]["identity_conflict"] is True
    assert merged[0]["status"] == "STARTED"


def test_round_reconciliation_promotes_only_complete_exact_message_request_round_and_seat_proof():
    record = _record()
    before = copy.deepcopy(record)
    original_round = record["rounds"][0]
    original_identity = {
        key: original_round[key]
        for key in (
            "round_id",
            "canonical_round_record_id",
            "canonical_identity_key",
            "conversation_id",
            "session_id",
            "message_id",
            "request_id",
            "round",
            "ordinal",
            "finished_at",
            "result_count",
            "created_at",
        )
    }

    repaired = reconcile_canonical_round_completion_statuses(record)

    assert repaired == 1
    assert record["rounds"][0]["status"] == "COMPLETED"
    for key, value in original_identity.items():
        assert record["rounds"][0][key] == value
    assert record["messages"] == before["messages"]
    assert record["requests"] == before["requests"]


def test_round_reconciliation_fails_closed_when_any_result_key_is_not_request_round_seat_bound():
    record = _record()
    record["requests"][0]["results"][1]["result_key"] = "wrong-key"

    repaired = reconcile_canonical_round_completion_statuses(record)

    assert repaired == 0
    assert record["rounds"][0]["status"] == "STARTED"


def test_round_reconciliation_fails_closed_when_request_is_not_completed():
    record = _record()
    record["requests"][0]["state"] = "RUNNING"

    repaired = reconcile_canonical_round_completion_statuses(record)

    assert repaired == 0
    assert record["rounds"][0]["status"] == "STARTED"


def test_round_reconciliation_fails_closed_when_user_message_binding_is_missing_or_ambiguous():
    missing = _record()
    missing["messages"] = []
    duplicate = _record()
    duplicate["messages"].append(copy.deepcopy(duplicate["messages"][0]))

    assert reconcile_canonical_round_completion_statuses(missing) == 0
    assert missing["rounds"][0]["status"] == "STARTED"
    assert reconcile_canonical_round_completion_statuses(duplicate) == 0
    assert duplicate["rounds"][0]["status"] == "STARTED"


def test_round_reconciliation_fails_closed_when_result_count_or_finished_timestamp_is_missing():
    wrong_count = _record()
    wrong_count["rounds"][0]["result_count"] = 3
    missing_finish = _record()
    missing_finish["rounds"][0].pop("finished_at")

    assert reconcile_canonical_round_completion_statuses(wrong_count) == 0
    assert wrong_count["rounds"][0]["status"] == "STARTED"
    assert reconcile_canonical_round_completion_statuses(missing_finish) == 0
    assert missing_finish["rounds"][0]["status"] == "STARTED"


def test_round_reconciliation_fails_closed_for_request_message_session_mismatch():
    record = _record()
    record["requests"][0]["session_id"] = "different-session"

    repaired = reconcile_canonical_round_completion_statuses(record)

    assert repaired == 0
    assert record["rounds"][0]["status"] == "STARTED"
