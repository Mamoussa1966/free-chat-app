from types import SimpleNamespace

from main import (
    _latest_seat_execution_result,
    _seat_execution_status,
    _seat_result_has_message,
)


def _request(request_id, results, state="COMPLETED"):
    return {"request_id": request_id, "state": state, "results": results}


def _result(seat, request_id, round_no, status, **kwargs):
    return {
        "seat": seat,
        "request_id": request_id,
        "round": round_no,
        "status": status,
        **kwargs,
    }


def test_latest_result_for_seat_uses_newest_request_and_round():
    chat = {
        "request_records": [
            _request("request-1", [
                _result("claude", "request-1", 1, "SUCCESS", classification="SUCCESS"),
            ]),
            _request("request-2", [
                _result("gemini", "request-2", 1, "SUCCESS", classification="SUCCESS"),
                _result(
                    "claude", "request-2", 1, "PROVIDER_ERROR",
                    classification="PROVIDER_ERROR",
                    dispatch_reason="READY_FREE_MODEL",
                    attempted_models=["claude-free-model"],
                    error="private transport detail must not reach UI",
                ),
                _result("claude", "request-2", 2, "RATE_LIMITED", classification="RATE_LIMITED"),
            ]),
        ]
    }

    latest = _latest_seat_execution_result(chat, "claude")

    assert latest is not None
    assert latest["request_id"] == "request-2"
    assert latest["round"] == 2
    assert latest["status"] == "RATE_LIMITED"
    assert "error" not in latest
    assert "private transport detail" not in str(latest)


def test_latest_result_is_scoped_to_the_requested_seat_and_its_request():
    chat = {
        "request_records": [
            _request("request-1", [
                _result("gemini", "request-1", 1, "SUCCESS"),
                _result("claude", "another-request", 1, "PROVIDER_ERROR"),
            ]),
        ]
    }

    assert _latest_seat_execution_result(chat, "gemini")["status"] == "SUCCESS"
    assert _latest_seat_execution_result(chat, "claude") is None


def test_missing_credentials_and_model_list_have_clear_non_failure_labels():
    missing_credentials = _seat_execution_status({
        "status": "NOT_CONFIGURED",
        "classification": "NOT_CONFIGURED",
        "dispatch_reason": "CREDENTIAL_MISSING",
        "request_id": "r1",
        "round": 1,
    })
    missing_models = _seat_execution_status({
        "status": "NOT_CONFIGURED",
        "classification": "NOT_CONFIGURED",
        "dispatch_reason": "FREE_MODEL_LIST_EMPTY",
        "request_id": "r2",
        "round": 1,
    })

    assert missing_credentials["status"] == "NOT_CONFIGURED"
    assert missing_credentials["reason"] == "اعتماد API غير متوفر لهذا المزوّد."
    assert missing_models["reason"] == "قائمة النماذج المجانية الصريحة غير مهيأة."


def test_provider_failure_is_readable_without_exposing_raw_error():
    status = _seat_execution_status({
        "status": "PROVIDER_ERROR",
        "classification": "PROVIDER_ERROR",
        "request_id": "r3",
        "round": 4,
        "attempted_models": ["provider-free-a", "provider-free-b"],
        "error": "api_key=NEVER_RENDER_THIS",
    })

    assert status["label"] == "فشل التنفيذ بعد قبول الإرسال"
    assert status["request_id"] == "r3"
    assert status["round"] == 4
    assert status["attempted_models"] == ["provider-free-a", "provider-free-b"]
    assert "NEVER_RENDER_THIS" not in str(status)
    assert "error" not in status


def test_success_is_matched_only_to_its_own_request_round_and_seat():
    seat = SimpleNamespace(key="gemini")
    result = {"request_id": "request-9", "round": 2}
    chat = {
        "messages": [
            {
                "request_id": "request-8",
                "round": 2,
                "seat_key": "gemini",
            },
            {
                "request_id": "request-9",
                "round": 1,
                "seat_key": "gemini",
            },
        ]
    }

    assert _seat_result_has_message(chat, seat, result) is False

    chat["messages"].append({
        "request_id": "request-9",
        "round": 2,
        "seat_key": "gemini",
    })
    assert _seat_result_has_message(chat, seat, result) is True


def test_malformed_round_values_do_not_break_message_lookup():
    seat = SimpleNamespace(key="gemini")
    chat = {"messages": [{"request_id": "r", "round": "not-a-number", "seat_key": "gemini"}]}

    assert _seat_result_has_message(chat, seat, {"request_id": "r", "round": 1}) is False


def test_missing_result_does_not_invent_a_provider_failure():
    assert _latest_seat_execution_result({"request_records": []}, "kimi") is None
    assert _latest_seat_execution_result({}, "kimi") is None
