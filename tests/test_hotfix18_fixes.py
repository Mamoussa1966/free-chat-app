from unittest.mock import patch
import providers


def test_legacy_authentication_label_is_terminal_by_public_classification():
    seat = next(s for s in providers.SEATS if s.key == "gemini")
    with patch("providers.call_official", side_effect=[providers.ProviderError("bad key", 401, "http_401_authentication_failed"), "must-not-run"]) as mocked:
        result = providers.call_seat(seat, "test", "", 1, False, "key", [], ("m1", "m2"), None, "RID")
    assert result["attempted_models"] == ["m1"]
    assert mocked.call_count == 1


def test_resource_exhausted_with_explicit_retry_is_rate_limited():
    body = '{"error":{"status":"RESOURCE_EXHAUSTED","message":"Too many requests. Please retry in 24 seconds."}}'
    assert providers._canonical_error_classification(providers._classify(429, body)) == "RATE_LIMITED"
