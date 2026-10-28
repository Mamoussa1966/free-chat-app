"""Cost-boundary regression tests for the strict live Bridge closure path."""

import main
from providers import Seat


def _seat(key: str, slot: int) -> Seat:
    return Seat(
        key, key.title(), key.title(),
        (f"{key.upper()}_API_KEY",),
        (f"{key.upper()}_FREE_MODELS",),
        "", key, slot,
    )


def test_strict_live_bridge_dispatches_only_deepseek_then_gemini():
    seats = (
        _seat("chatgpt", 1),
        _seat("gemini", 2),
        _seat("claude", 3),
        _seat("grok", 4),
        _seat("kimi", 5),
        _seat("deepseek", 7),
    )

    strict_keys = [
        seat.key for seat in main._round_provider_execution_order(
            seats, strict_live_bridge=True
        )
    ]
    assert strict_keys == ["deepseek", "gemini"]


def test_normal_round_keeps_existing_order_and_all_seats():
    seats = (
        _seat("chatgpt", 1),
        _seat("gemini", 2),
        _seat("claude", 3),
        _seat("grok", 4),
        _seat("kimi", 5),
        _seat("deepseek", 7),
    )

    normal_keys = [
        seat.key for seat in main._round_provider_execution_order(
            seats, strict_live_bridge=False
        )
    ]
    assert normal_keys == ["deepseek", "gemini", "chatgpt", "claude", "grok", "kimi"]


def test_strict_live_bridge_uses_only_known_working_models_present_in_explicit_list():
    candidates = {
        "deepseek": ("deepseek-flash", "deepseek-other"),
        "gemini": ("gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash"),
        "claude": ("claude-candidate-1", "claude-candidate-2"),
        "grok": ("grok-candidate-1", "grok-candidate-2"),
    }

    assert main._round_model_candidates("deepseek", candidates, True) == ("deepseek-flash",)
    assert main._round_model_candidates("gemini", candidates, True) == ("gemini-3.6-flash",)
    assert main._round_model_candidates("claude", candidates, True) == ()
    assert main._round_model_candidates("grok", candidates, True) == ()
    assert main._round_model_candidates("gemini", {"gemini": ("gemini-3.8-flash",)}, True) == ()


def test_normal_round_keeps_all_explicit_free_cascade_candidates():
    candidates = {
        "deepseek": ("deepseek-flash", "deepseek-other"),
        "gemini": ("gemini-3.8-flash", "gemini-other"),
    }

    assert main._round_model_candidates("deepseek", candidates, False) == candidates["deepseek"]
    assert main._round_model_candidates("gemini", candidates, False) == candidates["gemini"]
