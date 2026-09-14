import time
from unittest.mock import patch

import providers


def _gemini():
    return next(s for s in providers.get_seats() if s.key == "gemini")


def test_seat_budget_is_hard_two_seconds_and_cascade_gets_remaining_budget():
    seat = _gemini()
    calls = []

    def fake_call_official(*args, **kwargs):
        calls.append((args[4], kwargs.get("deadline")))
        if len(calls) == 1:
            raise providers.ProviderError("timeout", error_class="timeout")
        return "OK"

    with patch("providers.call_official", side_effect=fake_call_official):
        started = time.perf_counter()
        result = providers.call_seat(
            seat, "hello", "", 1, False, "key", [], ("m1", "m2")
        )
        elapsed = time.perf_counter() - started

    assert result["status"] == "SUCCESS"
    assert len(calls) == 2
    assert 0 < calls[0][0] <= 2.0
    assert 0 < calls[1][0] <= 2.0
    assert calls[1][0] <= calls[0][0]
    assert elapsed < 2.1


def test_deepseek_and_gemini_share_the_same_two_second_seat_contract():
    slots = {s.key: s.room_slot for s in providers.get_seats()}
    assert slots["gemini"] == 2
    assert slots["deepseek"] == 7
    assert providers.PROVIDER_SEAT_BUDGET_SECONDS == 2
    assert providers.CASCADE_MODEL_TIMEOUT_SECONDS == 2.0
