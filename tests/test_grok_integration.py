import time
from pathlib import Path
from unittest.mock import patch

import main
import providers
from providers import SEATS, call_seat, get_model_candidates

GROK = next(seat for seat in SEATS if seat.key == "grok")


def _response(status, text, payload=None, headers=None):
    class Response:
        status_code = status
        def __init__(self):
            self.text = text
            self.headers = headers or {}
        def json(self):
            return payload if payload is not None else {}
    return Response()


def _success(text="GROK_OK"):
    payload = {"id": "resp_test", "object": "response", "output_text": text, "output": []}
    return _response(200, str(payload), payload)


def test_grok_uses_explicit_grok_free_configuration_first():
    with patch("providers._read_setting", side_effect=lambda name: (
        ("grok-a,grok-b", "streamlit_secrets") if name == "GROK_FREE_MODELS" else
        (("xai-should-not-win", "environment") if name == "XAI_FREE_MODELS" else (None, "missing"))
    )):
        assert get_model_candidates(GROK) == ("grok-a", "grok-b")


def test_grok_uses_only_explicit_candidates_no_discovery():
    source = Path(providers.__file__).read_text(encoding="utf-8")
    assert "discover_grok_models" not in source
    assert "GROK_MODELS_ENDPOINT" not in source
    assert "list_grok_models" not in source


def test_grok_400_incorrect_api_key_is_authentication_error_and_stops():
    responses = [
        _response(400, '{"error":{"message":"incorrect API key provided"}}'),
        _success("SHOULD_NOT_RUN"),
    ]
    with patch("providers.requests.post", side_effect=responses) as post:
        result = call_seat(GROK, "Hello", "", 1, False, "fake-key", [], ("grok-a", "grok-b"))
    assert post.call_count == 1
    assert result["attempted_models"] == ["grok-a"]
    assert result["attempt_diagnostics"][0]["classification"] == "AUTHENTICATION_ERROR"
    assert result["attempt_summaries"][0]["status_code"] == 400


def test_grok_401_stops_cascade():
    response = _response(401, '{"error":{"message":"invalid authorization token"}}')
    with patch("providers.requests.post", return_value=response) as post:
        result = call_seat(GROK, "Hello", "", 1, False, "fake-key", [], ("grok-a", "grok-b"))
    assert post.call_count == 1
    assert result["attempted_models"] == ["grok-a"]
    assert result["attempt_diagnostics"][0]["classification"] == "AUTHENTICATION_ERROR"


def test_grok_model_unavailable_advances_to_next_model():
    responses = [
        _response(404, '{"error":{"message":"model not found"}}'),
        _success(),
    ]
    with patch("providers.requests.post", side_effect=responses) as post:
        result = call_seat(GROK, "Hello", "", 1, False, "fake-key", [], ("grok-old", "grok-good"))
    assert post.call_count == 2
    assert result["attempted_models"] == ["grok-old", "grok-good"]
    assert result["executed_model"] == "grok-good"
    assert result["attempt_diagnostics"][0]["classification"] == "MODEL_UNAVAILABLE"


def test_grok_429_rate_limit_advances_with_retry_policy():
    responses = [
        _response(429, '{"error":{"message":"too many requests"}}', headers={"Retry-After": "0"}),
        _response(429, '{"error":{"message":"too many requests"}}', headers={"Retry-After": "0"}),
        _success(),
    ]
    with patch("providers.requests.post", side_effect=responses) as post:
        result = call_seat(GROK, "Hello", "", 1, False, "fake-key", [], ("grok-a", "grok-b"))
    assert post.call_count == 3
    assert result["status"] == "SUCCESS"
    assert result["attempted_models"] == ["grok-a", "grok-b"]
    assert result["attempt_diagnostics"][0]["classification"] == "RATE_LIMITED"


def test_grok_quota_or_credit_exhaustion_is_not_transient_rate_limit():
    response = _response(429, '{"error":{"message":"credit balance exhausted"}}')
    with patch("providers.requests.post", return_value=response) as post:
        result = call_seat(GROK, "Hello", "", 1, False, "fake-key", [], ("grok-a", "grok-b"))
    assert post.call_count == 2
    assert result["attempted_models"] == ["grok-a", "grok-b"]
    assert result["attempt_diagnostics"][0]["classification"] == "QUOTA_EXCEEDED"


def test_grok_success_records_exact_executed_model_and_response_text():
    with patch("providers.requests.post", return_value=_success("GROK_OK")) as post:
        result = call_seat(GROK, "Hello", "", 1, False, "fake-key", [], ("grok-4-free",))
    assert post.call_count == 1
    assert result["status"] == "SUCCESS"
    assert result["content"] == "GROK_OK"
    assert result["model"] == result["executed_model"] == "grok-4-free"
    assert result["attempted_models"] == ["grok-4-free"]


def test_grok_live_failure_exposes_compact_attempt_summaries_only():
    responses = [
        _response(404, '{"error":{"message":"model not found; secret=DO_NOT_RENDER"}}'),
        _response(401, '{"error":{"message":"invalid API key; secret=DO_NOT_RENDER"}}'),
    ]
    with patch("providers.requests.post", side_effect=responses) as post:
        result = call_seat(GROK, "Hello", "", 1, False, "fake-key", [], ("grok-a", "grok-b"))
    assert post.call_count == 2
    assert result["attempted_models"] == ["grok-a", "grok-b"]
    assert [x["classification"] for x in result["attempt_summaries"]] == ["MODEL_UNAVAILABLE", "AUTHENTICATION_ERROR"]
    assert [x["status_code"] for x in result["attempt_summaries"]] == [404, 401]
    assert all("error" not in item for item in result["attempt_summaries"])
    assert "DO_NOT_RENDER" not in repr(result["attempt_summaries"])


def test_grok_public_history_never_persists_raw_provider_payload():
    raw = "HTTP 401 invalid API key raw-provider-secret https://example.invalid/private"
    public = main._public_result({
        "status": "FAILED", "model": "grok-a", "executed_model": "grok-a",
        "content": "", "error": raw, "attempted_models": ["grok-a"],
        "attempt_diagnostics": [{"attempt": 1, "model": "grok-a", "status_code": 401,
            "classification": "AUTHENTICATION_ERROR", "retryable": False,
            "error": raw, "_display_created_at": time.time()}],
    })
    assert "attempt_diagnostics" not in public
    assert "error" not in public
    assert public["attempt_summaries"][0]["classification"] == "AUTHENTICATION_ERROR"
    assert public["attempt_summaries"][0]["status_code"] == 401
    assert raw not in repr(public)


def test_grok_uses_same_shared_call_seat_path_as_gemini_and_claude():
    assert GROK.kind == "xai_responses"
    assert GROK.endpoint == "https://api.x.ai/v1/responses"
    assert GROK.model_env == ("GROK_FREE_MODELS", "XAI_FREE_MODELS")
