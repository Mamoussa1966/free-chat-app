from unittest.mock import patch

import providers


def test_cascade_has_no_artificial_seat_budget():
    seat = next(s for s in providers.get_seats() if s.key == "gemini")
    calls = []

    def fake_call_official(*args, **kwargs):
        calls.append((args[4], kwargs.get("deadline")))
        if len(calls) == 1:
            raise providers.ProviderError("provider error", error_class="timeout")
        return "OK"

    with patch("providers.call_official", side_effect=fake_call_official):
        result = providers.call_seat(
            seat, "hello", "", 1, False, "key", [], ("m1", "m2")
        )

    assert result["status"] == "SUCCESS"
    assert len(calls) == 2
    assert calls[0][0] is None
    assert calls[1][0] is None
    assert calls[0][1] is None and calls[1][1] is None


def test_deepseek_and_gemini_use_unlimited_time_contract():
    slots = {s.key: s.room_slot for s in providers.get_seats()}
    assert slots["gemini"] == 2
    assert slots["deepseek"] == 7
    assert providers.PROVIDER_SEAT_BUDGET_SECONDS is None
    assert providers.CASCADE_MODEL_TIMEOUT_SECONDS is None
