from unittest.mock import patch

import providers


def test_every_builtin_cascade_attempt_uses_exact_two_second_budget():
    seats = [s for s in providers.get_seats() if s.key != "deepseek"]
    seen = []

    def fake_call(*args, **kwargs):
        seen.append(args[4])
        return "OK"

    with patch("providers.call_official", side_effect=fake_call):
        for seat in seats:
            result = providers.call_seat(
                seat, "hello", "", 1, False, "key", [], ("model-1",)
            )
            assert result["status"] == "SUCCESS", (seat.key, result)

    assert seen
    assert all(value == 2.0 for value in seen)


def test_hidden_http_retries_cannot_extend_attempt_budget():
    assert providers.GEMINI_RETRIES == 0
    assert providers.RETRIES == 1  # low-level compatibility only; adapters pass retries=0
    assert providers.CASCADE_MODEL_TIMEOUT_SECONDS == 2.0
    assert providers.REQUEST_TIMEOUT == 2
