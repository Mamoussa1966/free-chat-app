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


def _success(text="GROK_OK", model="grok-good"):
    payload = {"id": "resp_test", "object": "response", "model": model, "output_text": text, "output": []}
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
        _success("SHOULD_NOT_RUN", "grok-b"),
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
        _success(model="grok-good"),
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
        _success(model="grok-b"),
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
    with patch("providers.requests.post", return_value=_success("GROK_OK", "grok-4-free")) as post:
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


def test_grok_invalid_api_key_code_and_provider_error_never_fall_to_unknown():
    assert providers._canonical_error_classification("invalid_api_key") == "AUTHENTICATION_ERROR"
    assert providers._canonical_error_classification("invalid_api_key") == "AUTHENTICATION_ERROR"
    assert providers._canonical_error_classification("provider_error") == "API_ERROR"


def test_grok_http_402_is_quota_exceeded():
    response = _response(402, '{"error":{"code":"insufficient_balance","message":"insufficient balance"}}')
    with patch("providers.requests.post", return_value=response) as post:
        result = call_seat(GROK, "Hello", "", 1, False, "fake-key", [], ("grok-a", "grok-b"))
    assert post.call_count == 2
    assert result["attempt_diagnostics"][0]["classification"] == "QUOTA_EXCEEDED"


def test_grok_realistic_invalid_api_key_payload_stops_cascade():
    response = _response(400, '{"error":{"type":"invalid_api_key","message":"Invalid API key"}}')
    with patch("providers.requests.post", return_value=response) as post:
        result = call_seat(GROK, "Hello", "", 1, False, "fake-key", [], ("grok-a", "grok-b"))
    assert post.call_count == 1
    assert result["attempted_models"] == ["grok-a"]
    assert result["attempt_diagnostics"][0]["classification"] == "AUTHENTICATION_ERROR"


def test_grok_unexpected_adapter_exception_is_normalized_and_keeps_cascade_diagnostics():
    calls = {"n": 0}
    def boom_then_success(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("xAI adapter shape changed")
        return "GROK_OK"
    with patch("providers.call_official", side_effect=boom_then_success):
        result = call_seat(GROK, "Hello", "", 1, False, "fake-key", [], ("grok-a", "grok-b"))
    assert result["status"] == "SUCCESS"
    assert result["attempted_models"] == ["grok-a", "grok-b"]
    assert result["executed_model"] == "grok-b"
    assert result["attempt_diagnostics"][0]["classification"] == "API_ERROR"


def test_grok_model_id_invalid_marker_is_model_unavailable():
    assert providers._canonical_error_classification(providers._classify(400, '{"error":{"code":"model_id_invalid"}}')) == "MODEL_UNAVAILABLE"


def test_grok_invalid_api_credential_marker_is_authentication_error():
    assert providers._canonical_error_classification(providers._classify(400, '{"error":{"code":"invalid_api_credential"}}')) == "AUTHENTICATION_ERROR"


def test_grok_structured_model_not_found_payload_is_model_unavailable():
    body = '{"error":{"code":"model_not_found","type":"invalid_request_error","message":"The requested model was not found"}}'
    assert providers._canonical_error_classification(providers._classify(404, body)) == "MODEL_UNAVAILABLE"


def test_grok_structured_permission_denied_is_authentication_error_and_terminal():
    response = _response(403, '{"error":{"code":"permission_denied","message":"API key or team does not have permission"}}')
    with patch("providers.requests.post", return_value=response) as post:
        result = call_seat(GROK, "Hello", "", 1, False, "fake-key", [], ("grok-a", "grok-b"))
    assert post.call_count == 1
    assert result["attempted_models"] == ["grok-a"]
    assert result["attempt_diagnostics"][0]["classification"] == "AUTHENTICATION_ERROR"


def test_grok_structured_rate_limit_code_is_rate_limited():
    body = '{"error":{"code":"rate_limit_exceeded","type":"rate_limit_error","message":"Too many requests"}}'
    assert providers._canonical_error_classification(providers._classify(429, body)) == "RATE_LIMITED"


def test_grok_structured_billing_code_is_quota_exceeded():
    body = '{"error":{"code":"insufficient_balance","type":"billing_error","message":"Insufficient balance"}}'
    assert providers._canonical_error_classification(providers._classify(402, body)) == "QUOTA_EXCEEDED"


def test_grok_structured_unknown_4xx_is_api_error_not_unknown():
    body = '{"error":{"code":"invalid_argument","message":"Unsupported request field"}}'
    assert providers._canonical_error_classification(providers._classify(422, body)) == "API_ERROR"


def test_grok_result_summaries_canonicalize_internal_provider_error_classes():
    with patch("providers.requests.post", return_value=_response(500, '{"error":{"message":"server failure"}}')) as post:
        result = call_seat(GROK, "Hello", "", 1, False, "fake-key", [], ("grok-a",))
    assert post.call_count == 2  # shared retry policy
    assert result["attempt_summaries"][-1]["classification"] == "API_ERROR"
    assert result["attempt_summaries"][-1]["classification"] in providers.ERROR_CLASSES


def test_grok_final_public_classification_is_never_internal_provider_class():
    result = main._public_result({
        "status": "FAILED", "model": "grok-a", "executed_model": "grok-a",
        "content": "", "error": "class=provider_error; failure",
        "attempted_models": ["grok-a"],
        "attempt_diagnostics": [{
            "attempt": 1, "model": "grok-a", "status_code": 500,
            "classification": "provider_error", "retryable": False,
        }],
    })
    assert result["attempt_summaries"][0]["classification"] == "API_ERROR"
    assert result["attempt_summaries"][0]["classification"] in {
        "MODEL_UNAVAILABLE", "QUOTA_EXCEEDED", "RATE_LIMITED",
        "AUTHENTICATION_ERROR", "API_ERROR", "NETWORK_ERROR", "TIMEOUT", "UNKNOWN"
    }


def test_grok_429_daily_quota_text_is_quota_exceeded():
    body = '{"error":{"message":"50 requests per day"}}'
    assert providers._canonical_error_classification(providers._classify(429, body)) == "QUOTA_EXCEEDED"


def test_grok_401_realistic_payload_is_terminal_via_public_classification():
    response = _response(401, '{"error":{"code":"invalid_api_key","message":"Invalid API key"}}')
    with patch("providers.requests.post", return_value=response) as post:
        result = call_seat(GROK, "Hello", "", 1, False, "fake-key", [], ("grok-a", "grok-b"))
    assert post.call_count == 1
    assert result["attempted_models"] == ["grok-a"]
    assert result["attempt_summaries"][-1]["classification"] == "AUTHENTICATION_ERROR"
