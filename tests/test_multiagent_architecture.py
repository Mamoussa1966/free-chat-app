import json
from unittest.mock import patch

import providers

def test_extra_agents_are_loaded_after_original_six_and_capped_at_twenty():
    extras = []
    for i in range(20):
        extras.append({
            "key": f"agent{i}", "name": f"Agent {i}",
            "credential_names": [f"AGENT_{i}_API_KEY"],
            "model_names": [f"AGENT_{i}_FREE_MODELS"],
            "endpoint": "https://example.invalid/v1/chat/completions",
            "kind": "chat_completions",
        })
    with patch("providers._setting", return_value=json.dumps(extras)):
        seats = providers.get_seats()
    assert [s.key for s in seats[:6]] == ["openai", "gemini", "claude", "grok", "kimi", "deepseek"]
    assert len(seats) == 20
    assert seats[-1].key == "agent13"

def test_extra_agent_credentials_and_models_are_explicit():
    config = [{
        "key": "perplexity", "name": "Perplexity",
        "credential_names": ["PERPLEXITY_API_KEY"],
        "model_names": ["PERPLEXITY_FREE_MODELS"],
        "endpoint": "https://api.perplexity.ai/chat/completions",
        "kind": "chat_completions",
    }]
    def setting(names):
        return json.dumps(config) if "AI_COUNCIL_EXTRA_AGENTS" in tuple(names) else None
    with patch("providers._setting", side_effect=setting):
        seat = next(s for s in providers.get_seats() if s.key == "perplexity")
        assert seat.env_names == ("PERPLEXITY_API_KEY",)
        assert seat.model_env == ("PERPLEXITY_FREE_MODELS",)

def test_invalid_extra_agent_is_ignored():
    config = [{"key": "bad key", "name": "Bad", "endpoint": "https://example.invalid", "credential_names": ["K"], "model_names": ["M"], "kind": "chat_completions"}]
    with patch("providers._setting", return_value=json.dumps(config)):
        assert len(providers.get_seats()) == 6


def test_main_executes_dynamic_get_seats_not_static_builtin_alias():
    from pathlib import Path
    source = Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8")
    assert "seats = get_seats()" in source
    assert "for seat in seats" in source
    assert "return [results[seat.key] for seat in seats]" in source


def test_deepseek_contract_is_explicit_and_independent():
    seat = next(s for s in providers.get_seats() if s.key == "deepseek")
    assert seat.env_names == ("DEEPSEEK_API_KEY",)
    assert seat.model_env == ("DEEPSEEK_FREE_MODELS",)
    assert seat.endpoint == "https://api.deepseek.com/chat/completions"
    assert seat.kind == "deepseek_chat"


def test_extra_agent_result_survives_real_round_aggregation(monkeypatch):
    """Integration regression: a dynamic extra seat must execute and survive aggregation."""
    from main import _run_council

    config = [{
        "key": "perplexity", "name": "Perplexity",
        "credential_names": ["PERPLEXITY_API_KEY"],
        "model_names": ["PERPLEXITY_FREE_MODELS"],
        "endpoint": "https://api.perplexity.ai/chat/completions",
        "kind": "chat_completions",
    }]

    def setting(names):
        return json.dumps(config) if "AI_COUNCIL_EXTRA_AGENTS" in tuple(names) else None

    def fake_call_seat(seat, user_prompt, shared_context, round_no, local_fallback, credential, attachments=None, model_candidates=None, deadline=None, request_id=""):
        model = (model_candidates or ("test-model",))[0]
        return {
            "seat": seat.key, "name": seat.name, "label": seat.label,
            "status": "SUCCESS", "mode": "official", "model": model,
            "executed_model": model, "provider_reported_model": model,
            "content": f"RESPONSE:{seat.key}", "error": None,
            "latency": 0.001, "attempted_models": [model],
            "attempt_diagnostics": [], "attempt_summaries": [],
            "official_authenticated": True, "request_id": request_id, "round": round_no,
        }

    monkeypatch.setattr(providers, "_setting", setting)
    import main
    monkeypatch.setattr(main, "call_seat", fake_call_seat)

    seats = main.get_seats()
    assert any(s.key == "perplexity" for s in seats)
    credentials = {s.key: "TEST_KEY" for s in seats}
    candidates = {s.key: ("test-model",) for s in seats}
    chat = {"messages": [], "request_ids": [], "request_records": [], "history_identity_ledger": [], "result_keys": []}

    results = _run_council(
        "hello", chat, 1, credentials, [], candidates,
        "user-message-1", "request-1"
    )

    extra = next(r for r in results if r["seat"] == "perplexity")
    assert extra["status"] == "SUCCESS"
    assert extra["content"] == "RESPONSE:perplexity"
    assert any(m.get("seat_key") == "perplexity" for m in chat["messages"])


def test_extra_agent_survives_diagnostic_aggregation(monkeypatch):
    """A configured extra seat must also appear in the complete diagnostic pass."""
    from main import _run_provider_diagnostics

    config = [{
        "key": "perplexity", "name": "Perplexity",
        "credential_names": ["PERPLEXITY_API_KEY"],
        "model_names": ["PERPLEXITY_FREE_MODELS"],
        "endpoint": "https://api.perplexity.ai/chat/completions",
        "kind": "chat_completions",
    }]

    def setting(names):
        return json.dumps(config) if "AI_COUNCIL_EXTRA_AGENTS" in tuple(names) else None

    def fake_diagnostic(seat, credential, model_candidates=None):
        return {
            "seat": seat.key, "name": seat.name, "label": seat.label,
            "status": "SUCCESS", "mode": "official",
            "model": (model_candidates or ("test-model",))[0],
            "executed_model": (model_candidates or ("test-model",))[0],
            "provider_reported_model": (model_candidates or ("test-model",))[0],
            "content": "", "error": None, "attempt_diagnostics": [],
        }

    monkeypatch.setattr(providers, "_setting", setting)
    import main
    monkeypatch.setattr(main, "diagnostic_seat", fake_diagnostic)

    seats = main.get_seats()
    credentials = {seat.key: "TEST_KEY" for seat in seats}
    candidates = {seat.key: ("test-model",) for seat in seats}
    results = _run_provider_diagnostics(credentials, candidates)

    extra = next(r for r in results if r["seat"] == "perplexity")
    assert extra["status"] == "SUCCESS"


def test_all_main_agent_surfaces_use_dynamic_registry():
    from pathlib import Path
    source = Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8")
    assert "from providers import SEATS" not in source
    assert "for s in SEATS" not in source
    # Every runtime surface must resolve the live registry, not the six-seat alias.
    assert source.count("seats = get_seats()") >= 3
    assert "results[seat.key]" in source
    assert "[results[seat.key] for seat in seats]" in source


def test_main_has_no_static_seats_registry_dependency():
    from pathlib import Path
    source = Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8")
    assert "from providers import SEATS" not in source
    assert "for s in SEATS" not in source
