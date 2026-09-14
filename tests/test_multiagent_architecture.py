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
    assert "for seat in get_seats()" in source
    assert "return [results[seat.key] for seat in get_seats()]" in source


def test_deepseek_contract_is_explicit_and_independent():
    seat = next(s for s in providers.get_seats() if s.key == "deepseek")
    assert seat.env_names == ("DEEPSEEK_API_KEY",)
    assert seat.model_env == ("DEEPSEEK_FREE_MODELS",)
    assert seat.endpoint == "https://api.deepseek.com/chat/completions"
    assert seat.kind == "deepseek_chat"
