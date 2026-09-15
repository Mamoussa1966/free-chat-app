from unittest.mock import patch

import providers


def test_builtin_cascade_attempts_have_no_artificial_timeout():
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
    assert all(value is None for value in seen)


def test_hidden_http_retries_remain_disabled():
    assert providers.GEMINI_RETRIES == 0
    assert providers.RETRIES == 1  # compatibility constant; adapters pass retries=0
    assert providers.CASCADE_MODEL_TIMEOUT_SECONDS is None
    assert providers.REQUEST_TIMEOUT is None
    assert providers.PROVIDER_SEAT_BUDGET_SECONDS is None
