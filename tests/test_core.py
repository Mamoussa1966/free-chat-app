import unittest
from unittest.mock import patch

from providers import (
    MAX_MODELS_PER_SEAT,
    SEATS,
    ProviderError,
    _classify,
    _parse_models,
    _retry_delay,
    _sanitize,
    call_seat,
    get_model_candidates,
)


class CoreTests(unittest.TestCase):
    def test_five_core_seats(self):
        self.assertEqual(len(SEATS), 5)
        self.assertEqual([s.key for s in SEATS], ["openai", "gemini", "claude", "grok", "kimi"])

    def test_model_parser_deduplicates_and_caps(self):
        raw = ",".join([f"m{i}" for i in range(15)] + ["m1", "bad model"])
        values = _parse_models(raw)
        self.assertEqual(len(values), MAX_MODELS_PER_SEAT)
        self.assertEqual(values[0], "m0")
        self.assertNotIn("bad model", values)

    def test_model_candidates_are_empty_without_explicit_configuration(self):
        with patch("providers._setting", return_value=None):
            self.assertEqual(get_model_candidates(SEATS[0]), ())

    def test_error_classification(self):
        self.assertEqual(_classify(401, "invalid api key"), "http_401_authentication_failed")
        self.assertEqual(_classify(404, "model not found"), "model_not_found_or_invalid")
        self.assertEqual(_classify(429, "credit_balance_exhausted"), "billing_or_quota")
        self.assertEqual(_classify(503, "server"), "provider_server")

    def test_retry_after_is_bounded(self):
        response = type("Response", (), {"headers": {"Retry-After": "999"}})()
        self.assertEqual(_retry_delay(response, 0), 5.0)

    def test_sanitize_redacts_explicit_secret(self):
        self.assertNotIn("super-secret-key", _sanitize("Authorization: Bearer super-secret-key", ["super-secret-key"]))

    def test_free_cascade_tries_next_model(self):
        errors = [
            ProviderError("quota", 429, "http_429_rate_limit_or_quota"),
            ProviderError("invalid model", 404, "model_not_found_or_invalid"),
        ]
        def fake_call(*args, **kwargs):
            if errors:
                raise errors.pop(0)
            return "FREE_OK"
        with patch("providers.call_official", side_effect=fake_call):
            result = call_seat(SEATS[0], "Hello", "", 1, False, "fake-key", [], ("free-1", "free-2", "free-3"))
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["attempted_models"], ["free-1", "free-2", "free-3"])
        self.assertTrue(result["official_authenticated"])

    def test_no_free_models_never_calls_provider(self):
        with patch("providers.call_official") as call:
            result = call_seat(SEATS[0], "Hello", "", 1, False, "fake-key", [], ())
        self.assertEqual(result["status"], "NO_FREE_MODEL_CONFIGURED")
        call.assert_not_called()

    def test_missing_credential_never_calls_provider(self):
        with patch("providers.call_official") as call:
            result = call_seat(SEATS[0], "Hello", "", 1, False, None, [], ("free-1",))
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("not_configured", result["error"])
        call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
