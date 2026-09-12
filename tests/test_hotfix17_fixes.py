from unittest.mock import patch
import providers


def _seat():
    return next(s for s in providers.SEATS if s.key == "gemini")


def _call(failures, models=("model-a", "model-b", "model-c")):
    with patch("providers.call_official", side_effect=failures):
        return providers.call_seat(_seat(), "test", "", 1, False, "dummy-secret-key", [], models, None, "RID")


def test_daily_quota_marker_is_quota_exceeded():
    assert providers._canonical_error_classification(providers._classify(429, "50 requests per day")) == "QUOTA_EXCEEDED"


def test_generic_429_is_rate_limited():
    assert providers._canonical_error_classification(providers._classify(429, "too many requests; retry in 10 seconds")) == "RATE_LIMITED"


def test_real_authentication_error_stops_cascade():
    result = _call([providers.ProviderError("HTTP 401: invalid api key", 401, "http_401_authentication_failed"), "should-not-run"])
    assert result["attempted_models"] == ["model-a"]
    assert result["attempt_diagnostics"][0]["classification"] == "AUTHENTICATION_ERROR"
