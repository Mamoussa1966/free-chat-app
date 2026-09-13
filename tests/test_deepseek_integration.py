import time
from pathlib import Path
from unittest.mock import patch

import main
import providers
from providers import SEATS, call_seat

DEEPSEEK = next(seat for seat in SEATS if seat.key == "deepseek")


def _response(status, text, payload=None, headers=None):
    class Response:
        status_code = status
        def __init__(self):
            self.text = text
            self.headers = headers or {}
        def json(self):
            return payload if payload is not None else {}
    return Response()


def test_deepseek_seat_uses_official_endpoint_and_explicit_free_catalog_only():
    assert DEEPSEEK.endpoint == "https://api.deepseek.com/chat/completions"
    assert DEEPSEEK.kind == "deepseek_chat"
    assert DEEPSEEK.env_names == ("DEEPSEEK_API_KEY",)
    assert DEEPSEEK.model_env == ("DEEPSEEK_FREE_MODELS",)


def test_deepseek_success_records_exact_executed_model():
    response = _response(200, '{"choices":[{"message":{"content":"DEEPSEEK_OK"}}]}', {"model": "configured-free-a", "choices": [{"message": {"content": "DEEPSEEK_OK"}}]})
    with patch("providers.requests.post", return_value=response) as post:
        result = call_seat(DEEPSEEK, "Hello", "", 1, False, "fake-key", [], ("configured-free-a",))
    assert post.call_count == 1
    assert post.call_args.kwargs["json"]["model"] == "configured-free-a"
    assert result["status"] == "SUCCESS"
    assert result["content"] == "DEEPSEEK_OK"
    assert result["model"] == result["executed_model"] == "configured-free-a"


def test_deepseek_401_stops_cascade():
    responses = [
        _response(401, '{"error":{"message":"invalid api key"}}'),
        _response(200, '{"choices":[{"message":{"content":"SHOULD_NOT_RUN"}}]}', {"model": "free-b", "choices": [{"message": {"content": "SHOULD_NOT_RUN"}}]}),
    ]
    with patch("providers.requests.post", side_effect=responses) as post:
        result = call_seat(DEEPSEEK, "Hello", "", 1, False, "fake-key", [], ("free-a", "free-b"))
    assert post.call_count == 1
    assert result["attempted_models"] == ["free-a"]
    assert result["attempt_diagnostics"][0]["classification"] == "AUTHENTICATION_ERROR"


def test_deepseek_model_unavailable_advances_cascade():
    responses = [
        _response(404, '{"error":{"message":"model not found"}}'),
        _response(200, '{"choices":[{"message":{"content":"DEEPSEEK_OK"}}]}', {"model": "good-model", "choices": [{"message": {"content": "DEEPSEEK_OK"}}]}),
    ]
    with patch("providers.requests.post", side_effect=responses) as post:
        result = call_seat(DEEPSEEK, "Hello", "", 1, False, "fake-key", [], ("old-model", "good-model"))
    assert post.call_count == 2
    assert result["attempted_models"] == ["old-model", "good-model"]
    assert result["executed_model"] == "good-model"
    assert result["attempt_diagnostics"][0]["classification"] == "MODEL_UNAVAILABLE"


def test_deepseek_429_quota_is_quota_exceeded_and_cascade_continues():
    responses = [
        _response(429, '{"error":{"message":"quota exceeded; daily limit reached"}}'),
        _response(200, '{"choices":[{"message":{"content":"DEEPSEEK_OK"}}]}', {"model": "free-b", "choices": [{"message": {"content": "DEEPSEEK_OK"}}]}),
    ]
    with patch("providers.requests.post", side_effect=responses) as post:
        result = call_seat(DEEPSEEK, "Hello", "", 1, False, "fake-key", [], ("free-a", "free-b"))
    assert post.call_count == 2
    assert result["status"] == "SUCCESS"
    assert result["attempt_diagnostics"][0]["classification"] == "QUOTA_EXCEEDED"


def test_deepseek_429_rate_limit_is_rate_limited_and_cascade_continues():
    responses = [
        _response(429, '{"error":{"message":"too many requests; retry-after 1"}}', headers={"Retry-After": "0"}),
        _response(429, '{"error":{"message":"too many requests; retry-after 1"}}', headers={"Retry-After": "0"}),
        _response(200, '{"choices":[{"message":{"content":"DEEPSEEK_OK"}}]}', {"model": "free-b", "choices": [{"message": {"content": "DEEPSEEK_OK"}}]}),
    ]
    with patch("providers.requests.post", side_effect=responses) as post:
        result = call_seat(DEEPSEEK, "Hello", "", 1, False, "fake-key", [], ("free-a", "free-b"))
    assert post.call_count == 3
    assert result["status"] == "SUCCESS"
    assert result["attempted_models"] == ["free-a", "free-b"]
    assert providers._canonical_error_classification(providers._classify(429, "too many requests; retry-after 1")) == "RATE_LIMITED"


def test_deepseek_history_is_compact_and_raw_payload_is_not_persisted():
    raw = "HTTP 401 secret=DO_NOT_PERSIST provider-json"
    public = main._public_result({
        "status": "FAILED", "model": "free-a", "executed_model": "free-a", "error": raw,
        "attempt_diagnostics": [{"attempt": 1, "model": "free-a", "status_code": 401,
            "classification": "AUTHENTICATION_ERROR", "retryable": False, "error": raw,
            "_display_created_at": time.time()}],
    })
    assert "attempt_diagnostics" not in public
    assert "error" not in public
    assert public["attempt_summaries"][0]["classification"] == "AUTHENTICATION_ERROR"
    assert raw not in repr(public)



def test_deepseek_api_key_exact_streamlit_secret_is_read(monkeypatch):
    import sys
    import types

    fake_streamlit = types.SimpleNamespace(secrets={"DEEPSEEK_API_KEY": "deepseek-test-secret"})
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

    present, value = providers._streamlit_secret_state("DEEPSEEK_API_KEY")
    assert present is True
    assert value == "deepseek-test-secret"
    assert providers.get_secret(("DEEPSEEK_API_KEY",)) == "deepseek-test-secret"


def test_deepseek_secret_wins_over_environment(monkeypatch):
    import sys
    import types

    fake_streamlit = types.SimpleNamespace(secrets={"DEEPSEEK_API_KEY": "secret-value"})
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "environment-value")

    assert providers.get_secret(("DEEPSEEK_API_KEY",)) == "secret-value"

def test_deepseek_is_not_given_an_implicit_free_model_catalog():
    source = Path(providers.__file__).read_text(encoding="utf-8")
    assert "DEEPSEEK_FREE_MODELS" in source
    assert "deepseek-v4-flash-free" not in source
    assert "deepseek-v4-pro-free" not in source


def test_deepseek_preserves_full_existing_test_set_plus_this_regression_module():
    root = Path(__file__).resolve().parents[1]
    names = {p.name for p in (root / "tests").glob("test_*.py") if p.is_file()}
    assert "test_deepseek_integration.py" in names
    assert len(names) == 34


def test_deepseek_secret_and_model_catalog_are_live_streamlit_settings(monkeypatch):
    import sys
    import types

    fake_streamlit = types.SimpleNamespace(secrets={
        "DEEPSEEK_API_KEY": "secret-key-value",
        "DEEPSEEK_FREE_MODELS": "deepseek-model-a,deepseek-model-b",
    })
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

    assert providers.get_secret(("DEEPSEEK_API_KEY",)) == "secret-key-value"
    assert providers.get_model_candidates(DEEPSEEK) == ("deepseek-model-a", "deepseek-model-b")
    assert providers.credential_config_sources()["deepseek"] == "streamlit_secrets"


def test_deepseek_secret_source_never_exposes_secret_value(monkeypatch):
    import sys
    import types

    secret = "secret-never-display-123456"
    fake_streamlit = types.SimpleNamespace(secrets={"DEEPSEEK_API_KEY": secret})
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

    source = providers.credential_config_sources()["deepseek"]
    assert source == "streamlit_secrets"
    assert secret not in source
