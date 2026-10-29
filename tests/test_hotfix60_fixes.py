import json
from pathlib import Path
from unittest.mock import patch

import providers
from providers import ProviderError, call_seat


def test_failed_result_exposes_safe_public_classification():
    # Keep the unit test deterministic and offline: a synthetic 503 response
    # exercises the public transient-provider classification without making a
    # real request to DeepSeek or relying on external network state.
    seat = next(s for s in providers.get_seats() if s.key == "deepseek")
    with patch(
        "providers.call_official",
        side_effect=ProviderError("synthetic upstream server error", 503, "transient_provider_error"),
    ) as mocked:
        result = call_seat(
            seat, "hello", "", 1, False, "TEST_KEY", [],
            ("deepseek-v4-flash",), request_id="hf60-classification"
        )
    assert mocked.call_count == 1
    assert result["status"] == "FAILED"
    assert result["classification"] == "TRANSIENT_PROVIDER_ERROR"
    assert "TEST_KEY" not in repr(result)


def test_missing_credential_is_authentication_classification():
    seat = next(s for s in providers.get_seats() if s.key == "deepseek")
    result = call_seat(
        seat, "hello", "", 1, False, None, [],
        ("deepseek-v4-flash",), request_id="hf60-missing-key"
    )
    assert result["status"] == "NOT_CONFIGURED"
    assert result["classification"] == "NOT_CONFIGURED"


def test_deepseek_payload_is_explicit_non_streaming_and_identity_attested():
    response = type("Response", (), {
        "status_code": 200,
        "text": '{"id":"hf60","model":"deepseek-v4-flash-0731","choices":[{"message":{"content":"OK"}}]}',
        "headers": {},
        "json": lambda self: {"id":"hf60","model":"deepseek-v4-flash-0731","choices":[{"message":{"content":"OK"}}]},
    })()
    seat = next(s for s in providers.get_seats() if s.key == "deepseek")
    with patch("providers.requests.post", return_value=response) as post:
        result = call_seat(
            seat, "hello", "", 1, False, "TEST_KEY", [],
            ("deepseek-v4-flash",), request_id="hf60-deepseek"
        )
    assert "json" not in post.call_args.kwargs
    payload = json.loads(post.call_args.kwargs["data"].decode("utf-8"))
    assert payload["model"] == "deepseek-v4-flash"
    assert payload["stream"] is False
    assert payload["thinking"]["type"] == providers.DEEPSEEK_THINKING_MODE
    assert result["status"] == "SUCCESS"
    assert result["executed_model"] == "deepseek-v4-flash"
    assert result["provider_reported_model"] == "deepseek-v4-flash-0731"


def test_provider_response_time_is_unlimited_and_has_no_hidden_retry():
    assert providers.GEMINI_REQUEST_TIMEOUT_SECONDS is None
    assert providers.CASCADE_MODEL_TIMEOUT_SECONDS is None
    assert providers.REQUEST_TIMEOUT is None
    assert providers.PROVIDER_SEAT_BUDGET_SECONDS is None
    assert providers.GEMINI_RETRIES == 0


def test_hotfix60_version_is_consistent():
    assert providers.VERSION == Path("VERSION.txt").read_text(encoding="utf-8").strip()
