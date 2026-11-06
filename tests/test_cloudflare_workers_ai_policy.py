from __future__ import annotations

import json
from unittest.mock import patch

import providers


MODEL = "@cf/zai-org/glm-4.7-flash"
ACCOUNT_ID = "a" * 32
TOKEN = "fake-cloudflare-token"


def _settings(values):
    def read(names):
        for name in names:
            if name in values:
                return values[name]
        return None
    return read


def _extra_config(endpoint=""):
    return json.dumps([{
        "key": "cloudflare_workers_ai",
        "name": "Cloudflare Workers AI",
        "credential_names": ["CLOUDFLARE_API_TOKEN"],
        "model_names": ["CLOUDFLARE_WORKERS_AI_FREE_MODELS"],
        "endpoint": endpoint,
        "kind": "cloudflare_workers_ai",
    }])


def _configured_values(**overrides):
    values = {
        "AI_COUNCIL_EXTRA_AGENTS": _extra_config(),
        "CLOUDFLARE_API_TOKEN": TOKEN,
        "CLOUDFLARE_ACCOUNT_ID": ACCOUNT_ID,
        "CLOUDFLARE_WORKERS_AI_FREE_MODELS": MODEL,
        "CLOUDFLARE_WORKERS_FREE_PLAN_CONFIRMED": "true",
    }
    values.update(overrides)
    return values


def _cloudflare_seat():
    return next(seat for seat in providers.get_seats() if seat.key == "cloudflare_workers_ai")


def test_cloudflare_agent_is_loaded_at_optional_dynamic_seat_8(monkeypatch):
    monkeypatch.setattr(providers, "_setting", _settings(_configured_values()))
    seat = _cloudflare_seat()

    assert seat.room_slot == 8
    assert seat.kind == "cloudflare_workers_ai"
    assert seat.env_names == ("CLOUDFLARE_API_TOKEN",)
    assert seat.model_env == ("CLOUDFLARE_WORKERS_AI_FREE_MODELS",)
    assert seat.endpoint == providers.CLOUDFLARE_WORKERS_AI_ENDPOINT


def test_cloudflare_reserved_seat_cannot_be_redirected_to_a_user_endpoint(monkeypatch):
    values = _configured_values()
    values["AI_COUNCIL_EXTRA_AGENTS"] = _extra_config("https://attacker.invalid/collect")
    monkeypatch.setattr(providers, "_setting", _settings(values))

    seat = _cloudflare_seat()
    assert seat.endpoint == providers.CLOUDFLARE_WORKERS_AI_ENDPOINT
    assert "attacker.invalid" not in seat.endpoint


def test_cloudflare_reserved_seat_pins_its_own_credential_and_model_names(monkeypatch):
    config = [{
        "key": "cloudflare_workers_ai",
        "name": "Cloudflare Workers AI",
        "credential_names": ["OPENAI_API_KEY"],
        "model_names": ["OPENAI_FREE_MODELS"],
        "endpoint": "https://attacker.invalid",
        "kind": "cloudflare_workers_ai",
    }]
    values = _configured_values(
        AI_COUNCIL_EXTRA_AGENTS=json.dumps(config),
        OPENAI_API_KEY="must-not-be-reused",
        OPENAI_FREE_MODELS=MODEL,
    )
    monkeypatch.setattr(providers, "_setting", _settings(values))
    seat = _cloudflare_seat()

    assert seat.env_names == ("CLOUDFLARE_API_TOKEN",)
    assert seat.model_env == ("CLOUDFLARE_WORKERS_AI_FREE_MODELS",)
    assert seat.endpoint == providers.CLOUDFLARE_WORKERS_AI_ENDPOINT


def test_cloudflare_kind_cannot_be_reused_by_another_dynamic_identity(monkeypatch):
    config = [{
        "key": "other_provider",
        "name": "Other",
        "credential_names": ["OTHER_API_TOKEN"],
        "model_names": ["OTHER_FREE_MODELS"],
        "endpoint": "https://example.invalid",
        "kind": "cloudflare_workers_ai",
    }]
    values = _configured_values(AI_COUNCIL_EXTRA_AGENTS=json.dumps(config))
    monkeypatch.setattr(providers, "_setting", _settings(values))
    assert all(seat.key != "other_provider" for seat in providers.get_seats())


def test_cloudflare_dispatch_is_blocked_without_explicit_workers_free_confirmation(monkeypatch):
    values = _configured_values(CLOUDFLARE_WORKERS_FREE_PLAN_CONFIRMED="false")
    monkeypatch.setattr(providers, "_setting", _settings(values))
    seat = _cloudflare_seat()

    assert providers.get_model_candidates_for_dispatch(seat) == ()
    assert "Workers Free" in providers.provider_zero_cost_policy_block_reason(seat)


def test_cloudflare_dispatch_requires_a_valid_account_id(monkeypatch):
    values = _configured_values(CLOUDFLARE_ACCOUNT_ID="not-an-account-id")
    monkeypatch.setattr(providers, "_setting", _settings(values))
    seat = _cloudflare_seat()

    assert providers.get_model_candidates_for_dispatch(seat) == ()
    assert "CLOUDFLARE_ACCOUNT_ID" in providers.provider_zero_cost_policy_block_reason(seat)


def test_cloudflare_allowlist_contains_only_the_verified_free_model(monkeypatch):
    values = _configured_values(
        CLOUDFLARE_WORKERS_AI_FREE_MODELS=(
            "@cf/zai-org/glm-4.7-flash,@cf/zai-org/glm-5.3,"
            "@cf/deepseek-ai/deepseek-v4.1-flash-1017"
        )
    )
    monkeypatch.setattr(providers, "_setting", _settings(values))
    seat = _cloudflare_seat()

    assert providers.get_model_candidates_for_dispatch(seat) == (MODEL,)


def test_cloudflare_dispatch_requires_the_api_token(monkeypatch):
    values = _configured_values(CLOUDFLARE_API_TOKEN="")
    monkeypatch.setattr(providers, "_setting", _settings(values))
    assert providers.get_model_candidates_for_dispatch(_cloudflare_seat()) == ()


def test_cloudflare_adapter_uses_only_official_endpoint_and_rejects_busy_requests(monkeypatch):
    values = _configured_values()
    monkeypatch.setattr(providers, "_setting", _settings(values))
    seat = _cloudflare_seat()
    response = {
        "model": MODEL,
        "choices": [{"message": {"content": "Cloudflare response"}}],
    }

    with patch("providers._post", return_value=response) as post:
        result = providers.call_official(seat, "hello", MODEL, TOKEN)

    assert result["text"] == "Cloudflare response"
    assert result["provider_reported_model"] == MODEL
    args, kwargs = post.call_args
    assert args[0] == providers.CLOUDFLARE_WORKERS_AI_ENDPOINT.format(account_id=ACCOUNT_ID)
    assert args[1]["Authorization"] == f"Bearer {TOKEN}"
    assert args[2]["model"] == MODEL
    assert args[2]["max_completion_tokens"] == providers.MAX_OUTPUT_TOKENS
    assert "max_tokens" not in args[2]
    assert args[2]["options"] == {"rejectIfBusy": True}
    assert args[2]["messages"][0]["content"] == "hello"
    assert args[-1] == 0


def test_cloudflare_direct_call_cannot_bypass_the_free_model_allowlist(monkeypatch):
    values = _configured_values()
    monkeypatch.setattr(providers, "_setting", _settings(values))
    seat = _cloudflare_seat()

    with patch("providers.call_official", side_effect=AssertionError("unapproved model must not be sent")):
        result = providers.call_seat(
            seat,
            "hello",
            "",
            1,
            False,
            TOKEN,
            model_candidates=("@cf/zai-org/glm-5.3",),
        )

    assert result["status"] == "NO_FREE_MODEL_CONFIGURED"
    assert result["attempted_models"] == []


def test_cloudflare_rate_or_quota_exhaustion_does_not_try_another_model(monkeypatch):
    values = _configured_values()
    monkeypatch.setattr(providers, "_setting", _settings(values))
    seat = _cloudflare_seat()

    with patch(
        "providers.call_official",
        side_effect=providers.ProviderError("daily neuron quota exhausted", 429, "billing_or_quota"),
    ) as call:
        result = providers.call_seat(
            seat,
            "hello",
            "",
            1,
            False,
            TOKEN,
            model_candidates=(MODEL,),
        )

    assert call.call_count == 1
    assert result["status"] == "FAILED"
    assert result["attempted_models"] == [MODEL]
    assert result["attempt_diagnostics"][0]["cascade_action"] == "CASCADE_STOP"
