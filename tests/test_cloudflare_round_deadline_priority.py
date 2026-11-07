from types import SimpleNamespace

import main


def _seat(key: str):
    return SimpleNamespace(key=key)


def test_deadline_bounded_normal_round_reserves_cloudflare_before_gemini():
    seats = tuple(
        _seat(key)
        for key in (
            "chatgpt",
            "gemini",
            "claude",
            "grok",
            "kimi",
            "deepseek",
            "cloudflare_workers_ai",
        )
    )

    ordered = main._round_provider_execution_order(
        seats,
        strict_live_bridge=False,
        protect_cloudflare_deadline=True,
    )

    assert [seat.key for seat in ordered] == [
        "deepseek",
        "cloudflare_workers_ai",
        "gemini",
        "chatgpt",
        "claude",
        "grok",
        "kimi",
    ]


def test_without_whole_request_deadline_normal_round_order_is_unchanged():
    seats = tuple(
        _seat(key)
        for key in (
            "chatgpt",
            "gemini",
            "claude",
            "grok",
            "kimi",
            "deepseek",
            "cloudflare_workers_ai",
        )
    )

    ordered = main._round_provider_execution_order(
        seats,
        strict_live_bridge=False,
        protect_cloudflare_deadline=False,
    )

    assert [seat.key for seat in ordered] == [
        "deepseek",
        "gemini",
        "chatgpt",
        "claude",
        "grok",
        "kimi",
        "cloudflare_workers_ai",
    ]


def test_strict_live_bridge_still_dispatches_only_deepseek_then_gemini():
    seats = tuple(
        _seat(key)
        for key in ("chatgpt", "gemini", "claude", "deepseek", "cloudflare_workers_ai")
    )

    ordered = main._round_provider_execution_order(
        seats,
        strict_live_bridge=True,
        protect_cloudflare_deadline=True,
    )

    assert [seat.key for seat in ordered] == ["deepseek", "gemini"]


def test_cloudflare_does_not_inherit_council_deadline_but_gemini_does():
    deadline = 12345.0

    assert main._provider_execution_deadline(
        _seat("cloudflare_workers_ai"), deadline
    ) is None
    assert main._provider_execution_deadline(_seat("gemini"), deadline) == deadline
    assert main._provider_execution_deadline(_seat("cloudflare_workers_ai"), None) is None
