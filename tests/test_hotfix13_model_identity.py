from unittest.mock import patch
import providers


def gemini_seat():
    return next(s for s in providers.SEATS if s.key == "gemini")


def run(candidates, failures):
    executed = []
    def fake_call_official(seat, prompt, model, credential, timeout, attachments=None, deadline=None):
        executed.append(model)
        if model in failures:
            raise providers.ProviderError("forced retryable failure", error_class="transient")
        return "OK"
    with patch("providers.call_official", side_effect=fake_call_official):
        result = providers.call_seat(gemini_seat(), "hello", "", 1, False, "key", [], tuple(candidates), None)
    return result, executed


def test_no_skip_from_1_to_3():
    result, executed = run(["m1", "m2", "m3"], {"m1", "m2"})
    assert executed == ["m1", "m2", "m3"]
    assert result["attempted_models"] == executed
    assert result["executed_model"] == "m3"
    assert result["model"] == result["executed_model"]


def test_first_candidate_success_stops_cascade():
    result, executed = run(["m1", "m2", "m3"], set())
    assert executed == ["m1"]
    assert result["attempted_models"] == ["m1"]
    assert result["model"] == result["executed_model"] == "m1"


def test_second_candidate_success_prevents_third():
    result, executed = run(["m1", "m2", "m3"], {"m1"})
    assert executed == ["m1", "m2"]
    assert "m3" not in executed
    assert result["model"] == result["executed_model"] == "m2"


def test_attempted_models_equal_actual_api_order():
    result, executed = run(["m1", "m2", "m3"], {"m1", "m2"})
    assert result["attempted_models"] == executed


def test_executed_model_is_last_actual_attempt():
    result, executed = run(["m1", "m2", "m3"], {"m1", "m2"})
    assert result["executed_model"] == executed[-1]
