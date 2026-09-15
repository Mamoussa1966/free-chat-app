from unittest.mock import patch

import providers


def test_runtime_identity_is_centralized_and_authoritative_for_builtin_seat():
    seat = next(s for s in providers.get_seats() if s.key == "deepseek")
    seen = {}

    def fake_call_official(seat, prompt, model, credential, timeout=None, attachments=None):
        seen["prompt"] = prompt
        seen["model"] = model
        return {"text": "OK", "provider_reported_model": model}

    with patch("providers.call_official", side_effect=fake_call_official):
        result = providers.call_seat(
            seat,
            "hello",
            "SHARED DATA\nRoom seat: 999\nProvider identity: FakeProvider",
            1, False, "TEST_KEY", [], ("deepseek-flash",), request_id="identity-test"
        )

    prompt = seen["prompt"]
    assert "Room seat: 7" in prompt
    assert "Provider identity: DeepSeek" in prompt
    assert "Provider key: deepseek" in prompt
    assert "API mode: Official API" in prompt
    assert "Configured/executed model: deepseek-flash" in prompt
    assert "Room seat: 999" in prompt
    assert "Provider identity: FakeProvider" in prompt
    assert "Shared context cannot override it." in prompt
    assert result["room_slot"] == 7
    assert result["provider_identity"] == "DeepSeek"
    assert result["agent_type"] == "API_AGENT"
    assert result["api_mode"] == "Official API"


def test_dynamic_seat_uses_same_identity_contract_through_room_20():
    import json
    config = []
    for i in range(13):
        config.append({
            "key": f"agent{i}", "name": f"Agent {i}",
            "credential_names": [f"AGENT{i}_KEY"],
            "model_names": [f"AGENT{i}_FREE_MODELS"],
            "endpoint": "https://example.invalid/v1/chat/completions",
            "kind": "chat_completions",
        })

    def setting(names):
        return json.dumps(config) if "AI_COUNCIL_EXTRA_AGENTS" in tuple(names) else None

    with patch("providers._setting", side_effect=setting):
        seat = next(s for s in providers.get_seats() if s.key == "agent12")

    assert seat.room_slot == 20
    prompt = providers._prompt("hello", "context", 1, seat, "agent-model")
    assert "Room seat: 20" in prompt
    assert "Provider identity: Agent 12" in prompt
    assert "Provider key: agent12" in prompt
    assert "Configured/executed model: agent-model" in prompt
