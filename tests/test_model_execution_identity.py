import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers import ProviderError, SEATS, call_seat


def _seat():
    return next(s for s in SEATS if s.key == "gemini")


def _call(seat, candidates, failures=()):
    executed = []

    def fake_call_official(seat, prompt, model, credential, timeout=45, attachments=None):
        executed.append(model)
        if model in set(failures):
            raise ProviderError("forced retryable failure", status_code=500, error_class="provider_server")
        return f"OK:{model}"

    with patch("providers.call_official", side_effect=fake_call_official):
        result = call_seat(
            seat, "hello", "", 1, False, "secret", [], tuple(candidates)
        )
    return result, executed


def test_first_candidate_success_executes_only_number_one():
    result, executed = _call(_seat(), ["free-1", "free-2", "free-3"])
    assert executed == ["free-1"]
    assert result["attempted_models"] == executed
    assert result["model"] == result["executed_model"] == "free-1"


def test_second_candidate_is_executed_before_third_and_third_is_not_used():
    result, executed = _call(_seat(), ["free-1", "free-2", "free-3"], failures=["free-1"])
    assert executed == ["free-1", "free-2"]
    assert "free-3" not in executed
    assert result["attempted_models"] == executed
    assert result["model"] == result["executed_model"] == "free-2"


def test_three_attempt_cascade_is_strictly_sequential_and_cannot_jump_1_to_3():
    result, executed = _call(
        _seat(),
        ["free-1", "free-2", "free-3"],
        failures=["free-1", "free-2"],
    )
    assert executed == ["free-1", "free-2", "free-3"], (
        "CASCADE ORDER VIOLATION: expected #1 -> #2 -> #3, got " + repr(executed)
    )
    assert result["attempted_models"] == executed
    assert result["model"] == result["executed_model"] == "free-3"


def test_attempted_models_must_equal_actual_api_execution_order():
    result, executed = _call(
        _seat(),
        ["free-1", "free-2", "free-3"],
        failures=["free-1", "free-2"],
    )
    assert result["attempted_models"] == executed
    assert result["attempted_models"] == ["free-1", "free-2", "free-3"]


def test_executed_model_must_be_last_actual_api_attempt():
    result, executed = _call(
        _seat(),
        ["free-1", "free-2", "free-3"],
        failures=["free-1", "free-2"],
    )
    assert executed
    assert result["executed_model"] == executed[-1]
    assert result["model"] == executed[-1]


def test_no_duplicate_model_execution():
    result, executed = _call(
        _seat(),
        ["free-1", "free-2", "free-3"],
        failures=["free-1", "free-2"],
    )
    assert len(executed) == len(set(executed))


def test_terminal_failure_stops_cascade_without_jumping_forward():
    executed = []

    def fake_call_official(seat, prompt, model, credential, timeout=45, attachments=None):
        executed.append(model)
        if model == "free-1":
            raise ProviderError("auth failure", status_code=401, error_class="authentication")
        return "SHOULD NOT RUN"

    with patch("providers.call_official", side_effect=fake_call_official):
        result = call_seat(
            _seat(), "hello", "", 1, False, "secret", [],
            ("free-1", "free-2", "free-3")
        )

    assert executed == ["free-1"]
    assert "free-2" not in executed
    assert "free-3" not in executed
    assert result["status"] == "FAILED"


def test_api_argument_identity_is_exact_model_being_executed():
    seen = []

    def fake_call_official(seat, prompt, model, credential, timeout=45, attachments=None):
        seen.append(model)
        if model == "free-1":
            raise ProviderError("temporary", error_class="provider_server")
        return "OK"

    with patch("providers.call_official", side_effect=fake_call_official):
        result = call_seat(
            _seat(), "hello", "", 1, False, "secret", [],
            ("free-1", "free-2", "free-3")
        )

    assert seen == ["free-1", "free-2"]
    assert result["executed_model"] == seen[-1]
    assert result["model"] == seen[-1]
