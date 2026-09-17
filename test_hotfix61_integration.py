import json
from pathlib import Path
from unittest.mock import patch

import providers


def test_room_has_exactly_20_total_seats_with_human_at_six():
    extras = [
        {
            "key": f"agent{i}",
            "name": f"Agent {i}",
            "credential_names": [f"AGENT_{i}_API_KEY"],
            "model_names": [f"AGENT_{i}_FREE_MODELS"],
            "endpoint": "https://example.invalid/v1/chat/completions",
            "kind": "chat_completions",
        }
        for i in range(20)
    ]
    with patch("providers._setting", return_value=json.dumps(extras)):
        seats = providers.get_seats()
    api_slots = [s.room_slot for s in seats]
    assert len(seats) == 19
    assert api_slots == [1, 2, 3, 4, 5, 7] + list(range(8, 21))
    assert 6 not in api_slots
    assert max(api_slots) == 20


def test_dynamic_agent_13_is_rejected_because_slot_20_is_the_room_limit():
    extras = [
        {
            "key": f"agent{i}",
            "name": f"Agent {i}",
            "credential_names": [f"AGENT_{i}_API_KEY"],
            "model_names": [f"AGENT_{i}_FREE_MODELS"],
            "endpoint": "https://example.invalid/v1/chat/completions",
            "kind": "chat_completions",
        }
        for i in range(14)
    ]
    with patch("providers._setting", return_value=json.dumps(extras)):
        seats = providers.get_seats()
    assert len(seats) == 19
    assert not any(s.key == "agent13" for s in seats)
    assert max(s.room_slot for s in seats) == 20


def test_gemini_failure_classification_survives_public_result_path():
    seat = next(s for s in providers.get_seats() if s.key == "gemini")
    with patch("providers._post", side_effect=providers.ProviderError("bad key", status_code=401, error_class="authentication")):
        result = providers.call_seat(
            seat, "hello", "", 1, False, "TEST_KEY", [], ("gemini-test",), request_id="g61", deadline=None
        )
    assert result["status"] == "FAILED"
    assert result["classification"] == "AUTHENTICATION_ERROR"
    assert result["attempt_diagnostics"][0]["classification"] == "AUTHENTICATION_ERROR"


def test_deepseek_payload_and_identity_attestation_are_fail_closed():
    seat = next(s for s in providers.get_seats() if s.key == "deepseek")
    seen = {}

    def fake_post(endpoint, headers, payload, timeout, deadline, retries=None):
        seen.update(payload)
        return {"model": "deepseek-v4-flash-0731", "choices": [{"message": {"content": "OK"}}]}

    with patch("providers._post", side_effect=fake_post):
        result = providers.call_seat(
            seat, "hello", "", 1, False, "TEST_KEY", [], ("deepseek-v4-flash",), request_id="d61", deadline=None
        )
    assert result["status"] == "SUCCESS"
    assert seen["model"] == "deepseek-v4-flash"
    assert seen["stream"] is False
    assert seen["thinking"] == {"type": providers.DEEPSEEK_THINKING_MODE}
    assert result["provider_reported_model"] == "deepseek-v4-flash-0731"
    assert result["executed_model"] == "deepseek-v4-flash"


def test_deepseek_mismatched_provider_identity_fails_closed():
    seat = next(s for s in providers.get_seats() if s.key == "deepseek")
    with patch("providers._post", return_value={"model": "deepseek-v4-pro", "choices": [{"message": {"content": "NO"}}]}):
        result = providers.call_seat(
            seat, "hello", "", 1, False, "TEST_KEY", [], ("deepseek-v4-flash",), request_id="d62", deadline=None
        )
    assert result["status"] == "FAILED"
    assert result["classification"] == "API_ERROR"
    assert result["attempt_diagnostics"][0]["error_class"] == "execution_identity_mismatch"


def test_dynamic_runtime_uses_get_seats_and_not_static_alias():
    source = Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8")
    assert "get_seats()" in source
    assert "seats = get_seats()" in source
