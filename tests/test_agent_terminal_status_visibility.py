from main import (
    _agent_terminal_status_presentation,
    _latest_seat_execution_result,
    _seat_result_has_visible_message,
)


def _record(request_id, state, results, created_at=""):
    return {
        "request_id": request_id,
        "state": state,
        "created_at": created_at,
        "rounds_executed": 2,
        "results": results,
    }


def _result(request_id, seat, round_no, status, **extra):
    row = {
        "request_id": request_id,
        "seat": seat,
        "round": round_no,
        "status": status,
        "classification": status,
        "result_key": f"{request_id}:{round_no}:{seat}",
        "content": "",
    }
    row.update(extra)
    return row


def test_latest_seat_result_uses_last_round_in_latest_request():
    chat = {
        "request_records": [
            _record("old-request", "COMPLETED", [
                _result("old-request", "gemini", 1, "SUCCESS", content="old reply")
            ]),
            _record("new-request", "COMPLETED", [
                _result("new-request", "gemini", 1, "SUCCESS", content="round one"),
                _result("new-request", "deepseek", 1, "SUCCESS", content="DeepSeek reply"),
                _result("new-request", "gemini", 2, "PROVIDER_ERROR", classification="AUTHENTICATION_ERROR"),
            ]),
        ]
    }

    latest = _latest_seat_execution_result(chat, "gemini")

    assert latest["request_id"] == "new-request"
    assert latest["round"] == 2
    assert latest["status"] == "PROVIDER_ERROR"
    assert latest["classification"] == "AUTHENTICATION_ERROR"


def test_latest_request_missing_seat_result_does_not_reuse_old_success():
    chat = {
        "request_records": [
            _record("old-request", "COMPLETED", [
                _result("old-request", "claude", 1, "SUCCESS", content="previous answer")
            ]),
            _record("new-request", "COMPLETED", [
                _result("new-request", "deepseek", 1, "SUCCESS", content="current answer")
            ]),
        ]
    }

    latest = _latest_seat_execution_result(chat, "claude")

    assert latest["request_id"] == "new-request"
    assert latest["status"] == "REQUEST_RESULT_MISSING"
    assert latest["source"] == "AUTHORITATIVE_REQUEST_RECORD"


def test_latest_seat_result_rejects_cross_request_rows():
    chat = {
        "request_records": [
            _record("new-request", "COMPLETED", [
                _result("old-request", "gemini", 3, "SUCCESS", content="must not leak"),
            ])
        ]
    }

    latest = _latest_seat_execution_result(chat, "gemini")

    assert latest["request_id"] == "new-request"
    assert latest["status"] == "REQUEST_RESULT_MISSING"


def test_dispatch_failure_explains_configuration_without_exposing_raw_error():
    presentation = _agent_terminal_status_presentation({
        "status": "NOT_CONFIGURED",
        "classification": "NOT_CONFIGURED",
        "dispatch_reason": "FREE_MODEL_LIST_EMPTY",
        "error": "private raw provider response must never be rendered",
    })

    assert presentation["kind"] == "warning"
    assert "غير مهيّأ" in presentation["title"]
    assert "قائمة النماذج المجانية" in presentation["detail"]
    assert "private raw provider response" not in repr(presentation)


def test_provider_failure_uses_safe_classification_not_raw_error():
    presentation = _agent_terminal_status_presentation({
        "status": "PROVIDER_ERROR",
        "classification": "AUTHENTICATION_ERROR",
        "dispatch_reason": "READY_FREE_MODEL",
        "error": "secret key and raw upstream body must never be displayed",
    })

    assert presentation["kind"] == "warning"
    assert "المصادقة" in presentation["detail"]
    assert "secret key" not in repr(presentation)
    assert "raw upstream body" not in repr(presentation)


def test_request_record_success_can_be_rendered_as_fallback_without_message_mutation():
    result = _result(
        "req-1", "gemini", 1, "SUCCESS",
        content="saved provider response",
    )
    presentation = _agent_terminal_status_presentation(result)

    assert presentation["kind"] == "success"
    assert "غير ظاهرة" in presentation["title"]
    assert result["content"] == "saved provider response"


def test_success_message_match_uses_request_and_round_identity():
    result = _result("req-1", "gemini", 2, "SUCCESS")
    matching_message = {
        "request_id": "req-1",
        "round": 2,
        "seat_key": "gemini",
        "result_key": "req-1:2:gemini",
    }
    other_round = {
        "request_id": "req-1",
        "round": 1,
        "seat_key": "gemini",
        "result_key": "req-1:1:gemini",
    }
    other_request = {
        "request_id": "old-req",
        "round": 2,
        "seat_key": "gemini",
        "result_key": "old-req:2:gemini",
    }

    assert _seat_result_has_visible_message(result, [matching_message]) is True
    assert _seat_result_has_visible_message(result, [other_round, other_request]) is False
