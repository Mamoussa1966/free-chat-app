import providers
import unittest
from unittest.mock import patch
import requests
from providers import ProviderError, _post, _prompt

class ProviderRuntimeTests(unittest.TestCase):
    def test_prompt_markers(self):
        text = _prompt("Hello", "CTX", 1)
        self.assertEqual(text.count("CURRENT USER REQUEST:"), 1)
        self.assertIn("UNTRUSTED SHARED CONTEXT", text)
    def test_billing_not_retried(self):
        response = type("Response", (), {"status_code": 429, "text": '{"error":"credit balance exhausted"}', "headers": {}, "json": lambda self: {}})()
        with patch("providers.requests.post", return_value=response) as post:
            with self.assertRaises(ProviderError): _post("https://example.invalid", {}, {}, 5)
        self.assertEqual(post.call_count, 1)
    def test_network_retries_once(self):
        response = type("Response", (), {"status_code": 200, "text": "{}", "headers": {}, "json": lambda self: {}})()
        with patch("providers.requests.post", side_effect=[requests.Timeout(), response]) as post:
            self.assertEqual(_post("https://example.invalid", {}, {}, 5), {})
        self.assertEqual(post.call_count, 2)

if __name__ == "__main__": unittest.main()


def test_404_model_classification_wins_over_quota_wording():
    assert providers._classify(404, "model not found; quota information unavailable") == "model_not_found_or_invalid"


def test_429_distinguishes_rate_limit_from_explicit_quota():
    assert providers._classify(429, "too many requests") == "http_429_rate_limit_or_quota"
    assert providers._classify(429, "quota exceeded") == "billing_or_quota"
