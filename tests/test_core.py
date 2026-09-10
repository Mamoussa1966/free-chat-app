import unittest
from unittest.mock import patch
from providers import MAX_MODELS_PER_SEAT, SEATS, ProviderError, _classify, _parse_models, _retry_delay, _sanitize, call_seat, get_model_candidates

class CoreTests(unittest.TestCase):
    def test_five_core_seats(self):
        self.assertEqual([s.key for s in SEATS], ["openai", "gemini", "claude", "grok", "kimi"])
    def test_model_parser_caps(self):
        self.assertEqual(len(_parse_models(",".join(f"m{i}" for i in range(20)))), MAX_MODELS_PER_SEAT)
    def test_model_candidates_empty_without_setting(self):
        with patch("providers._setting", return_value=None):
            self.assertEqual(get_model_candidates(SEATS[0]), ())

    def test_unicode_mobile_separators_are_normalized(self):
        raw = "gemini-a‚gemini-b،gemini-c，gemini-d؛gemini-e"
        self.assertEqual(_parse_models(raw), ("gemini-a", "gemini-b", "gemini-c", "gemini-d", "gemini-e"))

    def test_model_candidates_are_explicit_and_capped(self):
        configured = ",".join(f"model-{i}" for i in range(1, 13))
        with patch("providers._setting", return_value=configured):
            models = get_model_candidates(SEATS[1])
        self.assertEqual(len(models), MAX_MODELS_PER_SEAT)
        self.assertEqual(models[0], "model-1")
        self.assertEqual(models[-1], "model-10")
    def test_parser_rejects_path_traversal(self):
        self.assertEqual(_parse_models("good,foo/../bar,../evil,bar"), ("good", "bar"))
    def test_secret_precedence(self):
        with patch("providers._read_setting", side_effect=lambda name: ("secret-value", "streamlit_secrets") if name == "GEMINI_FREE_MODELS" else (None, "missing")):
            self.assertEqual(get_model_candidates(SEATS[1]), ("secret-value",))
    def test_classification(self):
        self.assertEqual(_classify(401, "invalid api key"), "http_401_authentication_failed")
        self.assertEqual(_classify(404, "model not found"), "model_not_found_or_invalid")
        self.assertEqual(_classify(429, "credit_balance_exhausted"), "billing_or_quota")
    def test_sanitize(self):
        self.assertNotIn("super-secret-key", _sanitize("Authorization: Bearer super-secret-key", ["super-secret-key"]))
    def test_free_cascade(self):
        errors = [ProviderError("quota", 429, "http_429_rate_limit_or_quota"), ProviderError("invalid model", 404, "model_not_found_or_invalid")]
        def fake(*args, **kwargs):
            if errors: raise errors.pop(0)
            return "FREE_OK"
        with patch("providers.call_official", side_effect=fake):
            result = call_seat(SEATS[0], "Hello", "", 1, False, "fake-key", [], ("free-1", "free-2", "free-3"))
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["attempted_models"], ["free-1", "free-2", "free-3"])
    def test_no_models_no_provider_call(self):
        with patch("providers.call_official") as call:
            result = call_seat(SEATS[0], "Hello", "", 1, False, "fake-key", [], ())
        self.assertEqual(result["status"], "NO_FREE_MODEL_CONFIGURED")
        call.assert_not_called()

if __name__ == "__main__": unittest.main()
