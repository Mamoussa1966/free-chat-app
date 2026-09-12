import time
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
        _response(200, '{"content":[{"type":"text","text":"CLAUDE_OK"}]}', {"content": [{"type": "text", "text": "CLAUDE_OK"}]}),
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
        _response(200, '{"content":[{"type":"text","text":"CLAUDE_OK"}]}', {"content": [{"type": "text", "text": "CLAUDE_OK"}]}),
    ]
    with patch("providers.requests.post", side_effect=responses) as post:
        result = call_seat(CLAUDE, "Hello", "", 1, False, "fake-key", [], ("free-1", "free-2"))
    assert post.call_count == 2
    assert result["attempted_models"] == ["free-1", "free-2"]
    assert result["executed_model"] == "free-2"
    assert result["attempt_diagnostics"][0]["classification"] == "MODEL_UNAVAILABLE"


def test_claude_success_records_executed_model_exactly():
    response = _response(200, '{"content":[{"type":"text","text":"CLAUDE_OK"}]}', {"content": [{"type": "text", "text": "CLAUDE_OK"}]})
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
