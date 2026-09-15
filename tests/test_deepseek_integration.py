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
    assert isinstance(post.call_args.kwargs["json"]["messages"][0]["content"], str)
    assert post.call_args.kwargs["json"]["messages"][0]["content"]
    assert result["status"] == "SUCCESS"
    assert result["content"] == "DEEPSEEK_OK"
    assert result["model"] == result["executed_model"] == "configured-free-a"


def test_deepseek_401_stops_cascade():
    responses = [
        _response(401, '{"error":{"message":"invalid api key"}}'),
        _response(200, '{"choices":[{"message":{"content":"SHOULD_NOT_RUN"}}]}', {"choices": [{"message": {"content": "SHOULD_NOT_RUN"}}]}),
    ]
    with patch("providers.requests.post", side_effect=responses) as post:
        result = call_seat(DEEPSEEK, "Hello", "", 1, False, "fake-key", [], ("free-a", "free-b"))
    assert post.call_count == 1
    assert result["attempted_models"] == ["free-a"]
    assert result["attempt_diagnostics"][0]["classification"] == "AUTHENTICATION_ERROR"


def test_deepseek_model_unavailable_advances_cascade():
    responses = [
        _response(404, '{"error":{"message":"model not found"}}'),
        _response(200, '{"model":"free-b","choices":[{"message":{"content":"DEEPSEEK_OK"}}]}', {"model": "free-b", "choices": [{"message": {"content": "DEEPSEEK_OK"}}]}),
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
        _response(200, '{"model":"free-b","choices":[{"message":{"content":"DEEPSEEK_OK"}}]}', {"model": "free-b", "choices": [{"message": {"content": "DEEPSEEK_OK"}}]}),
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
        _response(200, '{"model":"free-b","choices":[{"message":{"content":"DEEPSEEK_OK"}}]}', {"model": "free-b", "choices": [{"message": {"content": "DEEPSEEK_OK"}}]}),
    ]
    with patch("providers.requests.post", side_effect=responses) as post:
        result = call_seat(DEEPSEEK, "Hello", "", 1, False, "fake-key", [], ("free-a", "free-b"))
    assert post.call_count == 2
    assert result["status"] == "FAILED"
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



def test_deepseek_current_official_model_ids_are_supported_as_explicit_candidates():
    # Verified against the current official DeepSeek API documentation.
    # These IDs are API-valid; this test does NOT claim they are Free.
    official = ("deepseek-v4-flash", "deepseek-v4-pro", "deepseek-v4-flash-vision-exp")
    parsed = providers._parse_models(",".join(official))
    assert parsed == official
    assert all(model in parsed for model in official)


def test_deepseek_http_402_is_quota_exceeded():
    response = _response(402, '{"error":{"message":"insufficient balance"}}')
    with patch("providers.requests.post", return_value=response) as post:
        result = call_seat(DEEPSEEK, "Hello", "", 1, False, "fake-key", [], ("deepseek-v4-flash", "deepseek-v4-pro"))
    assert post.call_count == 2
    assert result["attempt_diagnostics"][0]["classification"] == "QUOTA_EXCEEDED"


def test_deepseek_500_is_api_error_and_can_advance():
    responses = [
        _response(400, '{"error":{"message":"invalid request parameter"}}'),
        _response(200, '{"model":"deepseek-v4-pro","choices":[{"message":{"content":"DEEPSEEK_OK"}}]}', {"model": "deepseek-v4-pro", "choices": [{"message": {"content": "DEEPSEEK_OK"}}]}),
    ]
    with patch("providers.requests.post", side_effect=responses) as post:
        result = call_seat(DEEPSEEK, "Hello", "", 1, False, "fake-key", [], ("deepseek-v4-flash", "deepseek-v4-pro"))
    assert post.call_count == 2
    assert result["status"] == "SUCCESS"
    assert result["attempt_diagnostics"][0]["classification"] == "API_ERROR"

def test_deepseek_explicit_api_error_advances_to_next_free_candidate():
    """Regression: a normalized API_ERROR on candidate #1 must not stop the cascade."""
    failures = [
        providers.ProviderError("temporary DeepSeek API failure", 503, "API_ERROR"),
    ]
    responses = [
        {"text": "DEEPSEEK_OK", "provider_reported_model": "deepseek-v4-pro"},
    ]
    with patch("providers.call_official", side_effect=failures + responses) as call:
        result = call_seat(DEEPSEEK, "Hello", "", 1, False, "fake-key", [],
                           ("deepseek-v4-flash", "deepseek-v4-pro"))
    assert call.call_count == 2
    assert result["status"] == "SUCCESS"
    assert result["attempted_models"] == ["deepseek-v4-flash", "deepseek-v4-pro"]
    assert result["executed_model"] == "deepseek-v4-pro"
    assert result["attempt_diagnostics"][0]["classification"] == "API_ERROR"
    assert result["attempt_diagnostics"][0]["retryable"] is True


def test_deepseek_is_not_given_an_implicit_free_model_catalog():
    source = Path(providers.__file__).read_text(encoding="utf-8")
    assert "DEEPSEEK_FREE_MODELS" in source
    assert "deepseek-v4-flash-free" not in source
    assert "deepseek-v4-pro-free" not in source


def test_deepseek_preserves_full_existing_test_set_plus_this_regression_module():
    root = Path(__file__).resolve().parents[1]
    names = {p.name for p in (root / "tests").glob("test_*.py") if p.is_file()}
    assert "test_deepseek_integration.py" in names
    import build_release
    assert names == build_release.EXPECTED_TEST_FILES


def test_deepseek_provider_model_is_attested_end_to_end():
    response = _response(200, '{"id":"r1","model":"deepseek-v4-flash","choices":[{"message":{"content":"IDENTITY_OK"}}]}', {"id": "r1", "model": "deepseek-v4-flash", "choices": [{"message": {"content": "IDENTITY_OK"}}]})
    with patch("providers.requests.post", return_value=response) as post:
        result = call_seat(DEEPSEEK, "identity", "", 1, False, "TEST_KEY", [], ("deepseek-v4-flash",), request_id="identity-1")
    assert post.call_count == 1
    assert post.call_args.kwargs["json"]["model"] == "deepseek-v4-flash"
    assert result["status"] == "SUCCESS"
    assert result["model"] == result["executed_model"] == result["provider_reported_model"] == "deepseek-v4-flash"


def test_deepseek_provider_model_mismatch_fails_closed():
    response = _response(200, '{"id":"r2","model":"different-model","choices":[{"message":{"content":"DO_NOT_ACCEPT"}}]}', {"id": "r2", "model": "different-model", "choices": [{"message": {"content": "DO_NOT_ACCEPT"}}]})
    with patch("providers.requests.post", return_value=response) as post:
        result = call_seat(DEEPSEEK, "identity", "", 1, False, "TEST_KEY", [], ("deepseek-v4-flash", "deepseek-v4-pro"), request_id="identity-2")
    assert post.call_count == 1
    assert result["status"] == "FAILED"
    assert result["attempted_models"] == ["deepseek-v4-flash"]
    assert result["attempt_diagnostics"][0]["error_class"] == "execution_identity_mismatch"


def test_deepseek_missing_provider_model_fails_closed():
    response = _response(200, '{"id":"r3","choices":[{"message":{"content":"NO_IDENTITY"}}]}', {"id": "r3", "choices": [{"message": {"content": "NO_IDENTITY"}}]})
    with patch("providers.requests.post", return_value=response) as post:
        result = call_seat(DEEPSEEK, "identity", "", 1, False, "TEST_KEY", [], ("deepseek-v4-flash",), request_id="identity-3")
    assert post.call_count == 1
    assert result["status"] == "FAILED"
    assert result["attempt_diagnostics"][0]["error_class"] == "execution_identity_mismatch"


def test_deepseek_secret_is_detected_from_streamlit_secrets(monkeypatch):
    import streamlit as st
    monkeypatch.setattr(st, "secrets", {
        "DEEPSEEK_API_KEY": "sk-test-deepseek",
        "DEEPSEEK_FREE_MODELS": "deepseek-v4-flash,deepseek-v4-pro",
    }, raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_FREE_MODELS", raising=False)

    assert providers.get_secret(("DEEPSEEK_API_KEY",)) == "sk-test-deepseek"
    assert providers.get_model_candidates(DEEPSEEK) == ("deepseek-v4-flash", "deepseek-v4-pro")
    assert providers.credential_sources()["deepseek"] == "streamlit_secrets"
    assert providers.model_config_sources()["deepseek"] == "streamlit_secrets"


def test_deepseek_secret_detection_accepts_case_and_nested_toml_keys(monkeypatch):
    import streamlit as st
    monkeypatch.setattr(st, "secrets", {
        "deepseek": {
            "api_key": "sk-nested",
            "free_models": "deepseek-v4-flash",
        }
    }, raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_FREE_MODELS", raising=False)

    assert providers.get_secret(("DEEPSEEK_API_KEY",)) == "sk-nested"
    assert providers.get_model_candidates(DEEPSEEK) == ("deepseek-v4-flash",)


def test_deepseek_streamlit_secret_resolver_handles_streamlit_like_object(monkeypatch):
    import streamlit as st

    class FakeSecrets:
        def __init__(self):
            self._data = {
                "DEEPSEEK_API_KEY": "sk-streamlit-like",
                "DEEPSEEK_FREE_MODELS": ["deepseek-chat", "deepseek-reasoner"],
            }
        def to_dict(self):
            return dict(self._data)
        def keys(self):
            return self._data.keys()
        def __getitem__(self, key):
            return self._data[key]
        def get(self, key, default=None):
            return self._data.get(key, default)

    monkeypatch.setattr(st, "secrets", FakeSecrets(), raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_FREE_MODELS", raising=False)

    assert providers.get_secret(("DEEPSEEK_API_KEY",)) == "sk-streamlit-like"
    assert providers.get_model_candidates(DEEPSEEK) == ("deepseek-chat", "deepseek-reasoner")
    assert providers.credential_sources()["deepseek"] == "streamlit_secrets"
    assert providers.model_config_sources()["deepseek"] == "streamlit_secrets"


def test_deepseek_secret_resolver_never_cross_binds_unrelated_generic_api_key(monkeypatch):
    import streamlit as st
    monkeypatch.setattr(st, "secrets", {
        "other_provider": {"api_key": "sk-other", "free_models": "other-model"},
        "deepseek": {"free_models": "deepseek-chat"},
    }, raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert providers.get_secret(("DEEPSEEK_API_KEY",)) is None
    assert providers.credential_sources()["deepseek"] == "missing"

def test_deepseek_secret_precedence_is_preserved(monkeypatch):
    import streamlit as st
    monkeypatch.setattr(st, "secrets", {"DEEPSEEK_API_KEY": "secret-value"}, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "environment-value")
    assert providers.get_secret(("DEEPSEEK_API_KEY",)) == "secret-value"
    assert providers.credential_sources()["deepseek"] == "streamlit_secrets"


def test_deepseek_secret_key_name_normalization_handles_bom_and_zero_width(monkeypatch):
    import streamlit as st
    monkeypatch.setattr(st, "secrets", {
        "\ufeffdeepseek_api_key\u200b": "sk-hidden-key",
        "\ufeffDEEPSEEK_FREE_MODELS\u200b": ["deepseek-chat", "deepseek-reasoner"],
    }, raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_FREE_MODELS", raising=False)

    assert providers.get_secret(("DEEPSEEK_API_KEY",)) == "sk-hidden-key"
    assert providers.get_model_candidates(DEEPSEEK) == ("deepseek-chat", "deepseek-reasoner")
    assert providers.credential_sources()["deepseek"] == "streamlit_secrets"
    assert providers.model_config_sources()["deepseek"] == "streamlit_secrets"


def test_deepseek_canonical_secret_wins_over_nested_same_provider_value(monkeypatch):
    import streamlit as st
    monkeypatch.setattr(st, "secrets", {
        "DEEPSEEK_API_KEY": "root-key",
        "deepseek": {"api_key": "nested-key"},
    }, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "environment-key")

    assert providers.get_secret(("DEEPSEEK_API_KEY",)) == "root-key"
    assert providers.credential_sources()["deepseek"] == "streamlit_secrets"


def test_deepseek_secret_materialized_toml_snapshot_is_used(monkeypatch):
    """Regression: resolve canonical DeepSeek keys from Streamlit's TOML snapshot."""
    import streamlit as st

    class SnapshotSecrets:
        def to_dict(self):
            return {
                "DEEPSEEK_API_KEY": "sk-snapshot-key",
                "DEEPSEEK_FREE_MODELS": "deepseek-v4-flash,deepseek-v4-pro",
            }
        def keys(self):
            return self.to_dict().keys()
        def __getitem__(self, key):
            return self.to_dict()[key]

    monkeypatch.setattr(st, "secrets", SnapshotSecrets(), raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_FREE_MODELS", raising=False)

    assert providers.get_secret(("DEEPSEEK_API_KEY",)) == "sk-snapshot-key"
    assert providers.get_model_candidates(DEEPSEEK) == (
        "deepseek-v4-flash", "deepseek-v4-pro"
    )
    assert providers.credential_sources()["deepseek"] == "streamlit_secrets"
    assert providers.model_config_sources()["deepseek"] == "streamlit_secrets"


def test_deepseek_real_adapter_builds_official_request_and_attests_response_model():
    """The adapter must send the selected model and require provider identity."""
    response = _response(
        200,
        '{"id":"r-real-shape","model":"deepseek-v4-flash","choices":[{"message":{"content":"OK"}}]}',
        {
            "id": "r-real-shape",
            "model": "deepseek-v4-flash",
            "choices": [{"message": {"content": "OK"}}],
        },
    )
    with patch("providers.requests.post", return_value=response) as post:
        result = call_seat(
            DEEPSEEK,
            "identity",
            "",
            1,
            False,
            "TEST_KEY",
            [],
            ("deepseek-v4-flash",),
            request_id="deepseek-real-shape-1",
        )

    assert post.call_count == 1
    assert post.call_args.args[0] == "https://api.deepseek.com/chat/completions"
    assert post.call_args.kwargs["json"]["model"] == "deepseek-v4-flash"
    assert result["status"] == "SUCCESS"
    assert result["provider_reported_model"] == "deepseek-v4-flash"
    assert result["executed_model"] == "deepseek-v4-flash"
    assert result["model"] == "deepseek-v4-flash"


def test_deepseek_secret_and_model_catalog_are_both_required_before_network(monkeypatch):
    """No DeepSeek request is allowed when either required setting is absent."""
    import streamlit as st
    monkeypatch.setattr(st, "secrets", {"DEEPSEEK_API_KEY": "sk-only"}, raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_FREE_MODELS", raising=False)

    assert providers.get_secret(("DEEPSEEK_API_KEY",)) == "sk-only"
    assert providers.get_model_candidates(DEEPSEEK) == ()



def test_deepseek_versioned_provider_identity_alias_is_accepted():
    assert providers._deepseek_model_identity_matches("deepseek-v4-flash", "deepseek-v4-flash-0731")
    assert providers._deepseek_model_identity_matches("deepseek-v4-pro", "deepseek-v4-pro-0813")
    assert not providers._deepseek_model_identity_matches("deepseek-v4-flash", "deepseek-v4-pro-0813")


def test_deepseek_versioned_provider_identity_alias_completes_successfully():
    response = _response(
        200,
        '{"id":"r4","model":"deepseek-v4-flash-0731","choices":[{"message":{"content":"ALIAS_OK"}}]}',
        {"id": "r4", "model": "deepseek-v4-flash-0731", "choices": [{"message": {"content": "ALIAS_OK"}}]},
    )
    with patch("providers.requests.post", return_value=response) as post:
        result = call_seat(
            DEEPSEEK, "identity", "", 1, False, "TEST_KEY", [],
            ("deepseek-v4-flash",), request_id="identity-4",
        )
    assert post.call_count == 1
    assert result["status"] == "SUCCESS"
    assert result["executed_model"] == "deepseek-v4-flash"
    assert result["provider_reported_model"] == "deepseek-v4-flash-0731"


def test_deepseek_api_error_explicitly_advances_to_second_free_candidate():
    """Regression: DeepSeek candidate #1 API_ERROR must advance to candidate #2."""
    failures = [providers.ProviderError("DeepSeek temporary API failure", 500, "API_ERROR")]
    responses = [{"text": "DEEPSEEK_V4_PRO_OK", "provider_reported_model": "deepseek-v4-pro"}]
    with patch("providers.call_official", side_effect=failures + responses) as call:
        result = call_seat(
            DEEPSEEK, "Hello", "", 1, False, "TEST_KEY", [],
            ("deepseek-v4-flash", "deepseek-v4-pro"),
            request_id="hotfix72-deepseek-api-error",
        )
    assert call.call_count == 2
    assert result["status"] == "SUCCESS"
    assert result["attempted_models"] == ["deepseek-v4-flash", "deepseek-v4-pro"]
    assert result["executed_model"] == "deepseek-v4-pro"
    assert result["provider_reported_model"] == "deepseek-v4-pro"
    assert result["attempt_summaries"][0]["classification"] == "API_ERROR"
    assert result["attempt_summaries"][0]["retryable"] is True


def test_deepseek_http_api_error_advances_via_actual_post_boundary():
    first = _response(500, '{"error":{"message":"temporary provider failure"}}')
    second = _response(200, '{"id":"r73","model":"deepseek-v4-pro","choices":[{"message":{"content":"DEEPSEEK_V4_PRO_OK"}}]}', {"id":"r73","model":"deepseek-v4-pro","choices":[{"message":{"content":"DEEPSEEK_V4_PRO_OK"}}]})
    with patch("providers.requests.post", side_effect=[first, second]) as post:
        result = call_seat(DEEPSEEK, "Hello", "", 1, False, "TEST_KEY", [],
                           ("deepseek-v4-flash", "deepseek-v4-pro"),
                           request_id="hotfix73-deepseek-http-api-error")
    assert post.call_count == 2
    assert result["status"] == "SUCCESS"
    assert result["attempted_models"] == ["deepseek-v4-flash", "deepseek-v4-pro"]
    assert result["executed_model"] == "deepseek-v4-pro"
    assert result["provider_reported_model"] == "deepseek-v4-pro"
    assert result["attempt_diagnostics"][0]["classification"] == "API_ERROR"
    assert result["attempt_diagnostics"][0]["retryable"] is True


def test_deepseek_http_200_error_envelope_advances_to_second_candidate():
    """HOTFIX82: a 200 error envelope is an API_ERROR, not an identity mismatch."""
    first = _response(200, '{"error":{"message":"temporary DeepSeek API failure"}}', {"error":{"message":"temporary DeepSeek API failure"}})
    second = _response(200, '{"id":"r74","model":"deepseek-v4-pro","choices":[{"message":{"content":"DEEPSEEK_V4_PRO_OK"}}]}', {"id":"r74","model":"deepseek-v4-pro","choices":[{"message":{"content":"DEEPSEEK_V4_PRO_OK"}}]})
    with patch("providers.requests.post", side_effect=[first, second]) as post:
        result = call_seat(DEEPSEEK, "Hello", "", 1, False, "TEST_KEY", [],
                           ("deepseek-v4-flash", "deepseek-v4-pro"),
                           request_id="hotfix74-deepseek-200-error")
    assert post.call_count == 2
    assert result["status"] == "SUCCESS"
    assert result["attempted_models"] == ["deepseek-v4-flash", "deepseek-v4-pro"]
    assert result["executed_model"] == "deepseek-v4-pro"
    assert result["attempt_diagnostics"][0]["classification"] == "API_ERROR"
    assert result["attempt_diagnostics"][0]["error_class"] == "API_ERROR"
    assert result["attempt_diagnostics"][0]["retryable"] is True


def test_deepseek_current_flash_identity_alias_is_accepted():
    """HOTFIX82: official current /models identity deepseek-flash is accepted."""
    response = _response(
        200,
        '{"id":"r74a","model":"deepseek-flash","choices":[{"message":{"content":"FLASH_OK"}}]}',
        {"id":"r74a","model":"deepseek-flash","choices":[{"message":{"content":"FLASH_OK"}}]},
    )
    with patch("providers.requests.post", return_value=response) as post:
        result = call_seat(DEEPSEEK, "identity", "", 1, False, "TEST_KEY", [],
                           ("deepseek-v4-flash",), request_id="hotfix74-deepseek-alias")
    assert post.call_count == 1
    assert result["status"] == "SUCCESS"
    assert result["executed_model"] == "deepseek-v4-flash"
    assert result["provider_reported_model"] == "deepseek-flash"


def test_deepseek_current_flash_identity_alias_is_accepted():
    assert providers._deepseek_model_identity_matches("deepseek-v4-flash", "deepseek-flash")
    assert not providers._deepseek_model_identity_matches("deepseek-v4-flash", "deepseek-v4-pro")
