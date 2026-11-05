from __future__ import annotations

from unittest.mock import patch

import providers


SEATS = {seat.key: seat for seat in providers.BUILTIN_SEATS}


def _setting(values):
    def read(names):
        for name in names:
            if name in values:
                return values[name]
        return None
    return read


def test_gemini_dispatch_requires_explicit_free_tier_confirmation(monkeypatch):
    values = {
        "GEMINI_API_KEY": "fake-gemini-key",
        "GEMINI_FREE_MODELS": "gemini-3.8-flash,gemini-3.6-flash",
    }
    monkeypatch.setattr(providers, "_setting", _setting(values))

    assert providers.get_model_candidates_for_dispatch(SEATS["gemini"]) == ()
    assert "Free Tier" in providers.provider_zero_cost_policy_block_reason(SEATS["gemini"])


def test_gemini_dispatch_filters_only_officially_listed_free_models(monkeypatch):
    values = {
        "GEMINI_API_KEY": "fake-gemini-key",
        "GEMINI_FREE_MODELS": (
            "gemini-3.8-flash,gemini-3.7-flash,gemini-3.6-flash,"
            "gemini-2.5-flash,gemini-2.0-flash,gemini-3.5-flash-lite"
        ),
        "GEMINI_API_ZERO_COST_CONFIRMED": "true",
    }
    monkeypatch.setattr(providers, "_setting", _setting(values))

    assert providers.get_model_candidates_for_dispatch(SEATS["gemini"]) == (
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
    )
    assert providers.provider_zero_cost_policy_block_reason(SEATS["gemini"]) == ""


def test_all_non_gemini_api_providers_are_blocked_before_provider_dispatch(monkeypatch):
    values = {
        "OPENAI_API_KEY": "fake-openai-key",
        "OPENAI_FREE_MODELS": "gpt-example",
        "ANTHROPIC_API_KEY": "fake-claude-key",
        "CLAUDE_FREE_MODELS": "claude-sonnet-example",
        "XAI_API_KEY": "fake-xai-key",
        "GROK_FREE_MODELS": "grok-example",
        "KIMI_API_KEY": "fake-kimi-key",
        "KIMI_FREE_MODELS": "kimi-example",
        "DEEPSEEK_API_KEY": "fake-deepseek-key",
        "DEEPSEEK_FREE_MODELS": "deepseek-example",
        "GEMINI_API_ZERO_COST_CONFIRMED": "true",
    }
    monkeypatch.setattr(providers, "_setting", _setting(values))

    for key in ("openai", "claude", "grok", "kimi", "deepseek"):
        seat = SEATS[key]
        assert providers.get_model_candidates_for_dispatch(seat) == ()
        assert "موقوف احترازيًا" in providers.provider_zero_cost_policy_block_reason(seat)


def test_non_gemini_diagnostic_does_not_probe_or_call_provider_api(monkeypatch):
    values = {
        "OPENAI_API_KEY": "fake-openai-key",
        "OPENAI_FREE_MODELS": "gpt-example",
    }
    monkeypatch.setattr(providers, "_setting", _setting(values))
    monkeypatch.setattr(
        providers,
        "_openai_models_probe",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("paid API probe must not run")),
    )
    monkeypatch.setattr(
        providers,
        "call_seat",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("provider API call must not run")),
    )

    result = providers.diagnostic_seat(SEATS["openai"], "fake-openai-key", ("gpt-example",))

    assert result["status"] == "NO_FREE_MODEL_CONFIGURED"
    assert result["dispatch_reason"] == "ZERO_COST_API_POLICY_BLOCKED"
    assert result["attempted_models"] == []
    assert result["runtime_execution_events"] == []


def test_voice_transcription_is_blocked_until_free_tier_is_confirmed(monkeypatch):
    values = {"GEMINI_API_KEY": "fake-gemini-key"}
    monkeypatch.setattr(providers, "_setting", _setting(values))
    monkeypatch.setattr(
        providers.requests,
        "post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("transcription API must not run")),
    )

    result = providers.transcribe_audio_gemini(
        b"audio-bytes",
        "audio/wav",
        "fake-gemini-key",
        ("gemini-3.8-flash",),
    )

    assert result["status"] == "FAILED"
    assert "zero_cost_policy_blocked" in result["error"]
    assert result["attempted_models"] == []


def test_voice_transcription_rejects_unapproved_model_ids_without_network(monkeypatch):
    values = {
        "GEMINI_API_KEY": "fake-gemini-key",
        "GEMINI_API_ZERO_COST_CONFIRMED": "true",
        "GEMINI_TRANSCRIBE_MODEL": "gemini-2.0-flash",
    }
    monkeypatch.setattr(providers, "_setting", _setting(values))
    monkeypatch.setattr(
        providers.requests,
        "post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unapproved model must not run")),
    )

    result = providers.transcribe_audio_gemini(
        b"audio-bytes",
        "audio/wav",
        "fake-gemini-key",
        (),
    )

    assert result["status"] == "FAILED"
    assert "transcriber_model_not_configured" in result["error"]
    assert result["attempted_models"] == []


def _openrouter_seat(
    *,
    endpoint=providers.OPENROUTER_ZERO_COST_ENDPOINT,
    kind="chat_completions",
    credential_names=("OPENROUTER_API_KEY",),
    model_names=("OPENROUTER_FREE_MODELS",),
):
    return providers.Seat(
        "openrouter",
        "OpenRouter Free",
        "🔑 OpenRouter Free",
        tuple(credential_names),
        tuple(model_names),
        endpoint,
        kind,
        8,
    )


def test_openrouter_only_accepts_explicit_free_variant_model_ids(monkeypatch):
    values = {
        "OPENROUTER_API_KEY": "fake-openrouter-key",
        "OPENROUTER_FREE_MODELS": (
            "openai/gpt-oss-20b:free,"
            "nvidia/nemotron-3-ultra:free,"
            "google/gemma-4-26b-a4b:free,"
            "openai/gpt-oss-120b,"
            "openrouter/free"
        ),
    }
    monkeypatch.setattr(providers, "_setting", _setting(values))
    seat = _openrouter_seat()

    assert providers.provider_zero_cost_policy_block_reason(seat) == ""
    assert providers.get_model_candidates_for_dispatch(seat) == (
        "openai/gpt-oss-20b:free",
        "nvidia/nemotron-3-ultra:free",
        "google/gemma-4-26b-a4b:free",
    )


def test_openrouter_rejects_automatic_router_and_paid_candidates(monkeypatch):
    values = {
        "OPENROUTER_API_KEY": "fake-openrouter-key",
        "OPENROUTER_FREE_MODELS": "openrouter/free,openai/gpt-oss-120b",
    }
    monkeypatch.setattr(providers, "_setting", _setting(values))

    assert providers.get_model_candidates_for_dispatch(_openrouter_seat()) == ()


def test_openrouter_rejects_noncanonical_endpoint_adapter_and_secret_names():
    bad_seats = [
        _openrouter_seat(endpoint="https://attacker.invalid/api/v1/chat/completions"),
        _openrouter_seat(kind="openai_responses"),
        _openrouter_seat(credential_names=("OPENAI_API_KEY",)),
        _openrouter_seat(model_names=("OPENAI_FREE_MODELS",)),
    ]
    for seat in bad_seats:
        reason = providers.provider_zero_cost_policy_block_reason(seat)
        assert "إعداد OpenRouter" in reason
        assert providers.get_model_candidates_for_dispatch(seat) == ()


def test_openrouter_diagnostic_never_dispatches_paid_or_automatic_model_ids(monkeypatch):
    values = {
        "OPENROUTER_API_KEY": "fake-openrouter-key",
        "OPENROUTER_FREE_MODELS": "openai/gpt-oss-20b:free",
    }
    monkeypatch.setattr(providers, "_setting", _setting(values))
    monkeypatch.setattr(
        providers,
        "call_seat",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("non-free diagnostic must not call API")),
    )

    seat = _openrouter_seat()
    result = providers.diagnostic_seat(
        seat,
        "fake-openrouter-key",
        ("openai/gpt-oss-120b", "openrouter/free"),
    )

    assert result["status"] == "NO_FREE_MODEL_CONFIGURED"
    assert result["dispatch_reason"] == "ZERO_COST_MODEL_NOT_CONFIGURED"
    assert result["attempted_models"] == []
    assert result["runtime_execution_events"] == []
