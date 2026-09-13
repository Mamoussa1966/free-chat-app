import time
from pathlib import Path
from unittest.mock import patch

import requests

import main
import providers
from providers import SEATS, call_seat

CLAUDE = next(seat for seat in SEATS if seat.key == "claude")


def _response(status, text, payload=None, headers=None):
    class Response:
        status_code = status
        def __init__(self):
            self.text = text
            self.headers = headers or {}
        def json(self):
            return payload if payload is not None else {}
    return Response()


def test_claude_real_http_path_401_stops_cascade():
    responses = [
        _response(401, '{"error":{"type":"authentication_error","message":"invalid x-api-key"}}'),
        _response(200, '{"content":[{"type":"text","text":"SHOULD_NOT_RUN"}]}', {"content": [{"type": "text", "text": "SHOULD_NOT_RUN"}]}),
    ]
    with patch("providers.requests.post", side_effect=responses) as post:
        result = call_seat(CLAUDE, "Hello", "", 1, False, "fake-key", [], ("free-1", "free-2"))
    assert post.call_count == 1
    assert result["status"] == "FAILED"
    assert result["attempted_models"] == ["free-1"]
    assert result["attempt_diagnostics"][0]["classification"] == "AUTHENTICATION_ERROR"


def test_claude_429_quota_is_not_rate_limit():
    response = _response(429, '{"error":{"type":"rate_limit_error","message":"daily limit reached; 50 requests per day"}}')
    with patch("providers.requests.post", return_value=response) as post:
        result = call_seat(CLAUDE, "Hello", "", 1, False, "fake-key", [], ("free-1", "free-2"))
    assert post.call_count == 2
    assert result["attempt_diagnostics"][0]["classification"] == "QUOTA_EXCEEDED"
    assert result["attempted_models"] == ["free-1", "free-2"]


def test_claude_429_transient_rate_limit_advances_cascade():
    responses = [
        _response(429, '{"error":{"type":"rate_limit_error","message":"too many requests"}}', headers={"Retry-After": "0"}),
        _response(429, '{"error":{"type":"rate_limit_error","message":"too many requests"}}', headers={"Retry-After": "0"}),
        _response(200, '{"content":[{"type":"text","text":"CLAUDE_OK"}]}', {"model": "free-2", "content": [{"type": "text", "text": "CLAUDE_OK"}]}),
    ]
    with patch("providers.requests.post", side_effect=responses) as post:
        result = call_seat(CLAUDE, "Hello", "", 1, False, "fake-key", [], ("free-1", "free-2"))
    assert post.call_count == 3
    assert result["status"] == "SUCCESS"
    assert result["attempted_models"] == ["free-1", "free-2"]
    assert result["executed_model"] == "free-2"
    assert result["attempt_diagnostics"][0]["classification"] == "RATE_LIMITED"


def test_claude_model_unavailable_advances_to_next_model():
    responses = [
        _response(404, '{"error":{"type":"not_found_error","message":"model not found"}}'),
        _response(200, '{"content":[{"type":"text","text":"CLAUDE_OK"}]}', {"model": "free-2", "content": [{"type": "text", "text": "CLAUDE_OK"}]}),
    ]
    with patch("providers.requests.post", side_effect=responses) as post:
        result = call_seat(CLAUDE, "Hello", "", 1, False, "fake-key", [], ("free-1", "free-2"))
    assert post.call_count == 2
    assert result["attempted_models"] == ["free-1", "free-2"]
    assert result["executed_model"] == "free-2"
    assert result["attempt_diagnostics"][0]["classification"] == "MODEL_UNAVAILABLE"


def test_claude_success_records_executed_model_exactly():
    response = _response(200, '{"model":"free-1","content":[{"type":"text","text":"CLAUDE_OK"}]}', {"model": "free-1", "content": [{"type": "text", "text": "CLAUDE_OK"}]})
    with patch("providers.requests.post", return_value=response) as post:
        result = call_seat(CLAUDE, "Hello", "", 1, False, "fake-key", [], ("free-1",))
    assert post.call_count == 1
    assert result["content"] == "CLAUDE_OK"
    assert result["model"] == result["executed_model"] == "free-1"


def test_claude_history_is_compact_and_raw_diagnostics_are_not_persisted():
    raw = "HTTP 401 raw-secret-payload https://example.invalid/private"
    public = main._public_result({
        "status": "FAILED",
        "model": "free-1",
        "executed_model": "free-1",
        "content": "",
        "error": raw,
        "attempt_diagnostics": [{
            "attempt": 1,
            "model": "free-1",
            "status_code": 401,
            "classification": "AUTHENTICATION_ERROR",
            "retryable": False,
            "error": raw,
            "_display_created_at": time.time(),
        }],
    })
    assert "attempt_diagnostics" not in public
    assert "error" not in public
    assert public["attempt_summaries"][0]["classification"] == "AUTHENTICATION_ERROR"
    assert raw not in repr(public)


def test_claude_uses_only_explicit_free_configuration():
    candidates = {seat.key: () for seat in providers.SEATS}
    candidates["claude"] = ("configured-free-a", "configured-free-b")
    assert candidates["claude"] == ("configured-free-a", "configured-free-b")

def test_claude_has_no_dynamic_model_discovery_path():
    source_main = open("main.py", encoding="utf-8").read()
    source_providers = open("providers.py", encoding="utf-8").read()
    assert "discover_claude_models" not in source_main
    assert "CLAUDE_MODELS_ENDPOINT" not in source_providers
    assert "claude_model_discovery" not in source_main


def test_claude_uses_the_same_explicit_candidate_path_as_gemini():
    source_main = Path(main.__file__).read_text(encoding="utf-8")
    assert "_claude_execution_candidates" not in source_main
    assert "claude_custom_model" not in source_main


def test_claude_400_model_error_is_model_unavailable_and_advances():
    responses = [
        _response(400, '{"error":{"type":"invalid_request_error","message":"model claude-old is not available"}}'),
        _response(200, '{"content":[{"type":"text","text":"CLAUDE_OK"}]}', {"model": "claude-good", "content": [{"type": "text", "text": "CLAUDE_OK"}]}),
    ]
    with patch("providers.requests.post", side_effect=responses) as post:
        result = call_seat(CLAUDE, "Hello", "", 1, False, "fake-key", [], ("claude-old", "claude-good"))
    assert post.call_count == 2
    assert result["attempted_models"] == ["claude-old", "claude-good"]
    assert result["executed_model"] == "claude-good"
    assert result["attempt_diagnostics"][0]["classification"] == "MODEL_UNAVAILABLE"


def test_claude_public_failure_result_keeps_status_and_classification_without_raw_payload():
    raw = "HTTP 401 invalid x-api-key super-secret-provider-payload"
    public = main._public_result({
        "status": "FAILED", "model": "claude-opus-5", "executed_model": "claude-opus-5",
        "content": "", "error": raw, "attempted_models": ["claude-opus-5"],
        "attempt_diagnostics": [{"attempt": 1, "model": "claude-opus-5", "status_code": 401,
            "classification": "AUTHENTICATION_ERROR", "retryable": False, "error": raw, "_display_created_at": time.time()}],
    })
    assert public["attempted_models"] == ["claude-opus-5"]
    assert public["attempt_summaries"][0]["classification"] == "AUTHENTICATION_ERROR"
    assert public["attempt_summaries"][0]["status_code"] == 401
    assert "attempt_diagnostics" not in public and "error" not in public
    assert raw not in repr(public)


def test_claude_failure_result_exposes_only_compact_attempt_summaries_to_live_ui():
    responses = [
        _response(404, '{"error":{"type":"not_found_error","message":"model not found"}}'),
        _response(401, '{"error":{"type":"authentication_error","message":"invalid x-api-key; secret=DO_NOT_RENDER"}}'),
    ]
    with patch("providers.requests.post", side_effect=responses) as post:
        result = call_seat(CLAUDE, "Hello", "", 1, False, "fake-key", [], ("claude-opus-5", "claude-sonnet-5"))
    assert post.call_count == 2
    assert result["attempted_models"] == ["claude-opus-5", "claude-sonnet-5"]
    assert result["attempt_summaries"] == [
        {
            "attempt": 1,
            "model": "claude-opus-5",
            "status_code": 404,
            "classification": "MODEL_UNAVAILABLE",
            "retryable": True,
            "created_at_epoch": result["attempt_summaries"][0]["created_at_epoch"],
        },
        {
            "attempt": 2,
            "model": "claude-sonnet-5",
            "status_code": 401,
            "classification": "AUTHENTICATION_ERROR",
            "retryable": False,
            "created_at_epoch": result["attempt_summaries"][1]["created_at_epoch"],
        },
    ]
    assert all("error" not in item for item in result["attempt_summaries"])
    assert "DO_NOT_RENDER" not in repr(result["attempt_summaries"])
