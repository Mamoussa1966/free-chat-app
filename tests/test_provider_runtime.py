import unittest
from unittest.mock import patch
import requests
from providers import ProviderError, SEATS, _post, _prompt, _validate_gemini_model

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
    def test_gemini_model_validation_accepts_official_generate_content_model(self):
        response = type("Response", (), {"status_code": 200, "text": '{"name":"models/gemini-3.8-flash","supportedGenerationMethods":["generateContent"]}', "headers": {}, "json": lambda self: {"name":"models/gemini-3.8-flash", "supportedGenerationMethods":["generateContent"]}})()
        with patch("providers.requests.get", return_value=response):
            ok, reason = _validate_gemini_model("gemini-3.8-flash", "test-key-123456")
        self.assertTrue(ok)
        self.assertIn("model_validated", reason)

    def test_gemini_model_validation_rejects_unknown_model(self):
        response = type("Response", (), {"status_code": 404, "text": '{"error":{"message":"Model not found"}}', "headers": {}, "json": lambda self: {"error":{"message":"Model not found"}}})()
        with patch("providers.requests.get", return_value=response):
            ok, reason = _validate_gemini_model("gemini-3.7-flash", "test-key-654321")
        self.assertFalse(ok)
        self.assertIn("invalid_model_id", reason)

    def test_gemini_model_validation_rejects_model_without_generate_content(self):
        response = type("Response", (), {"status_code": 200, "text": '{"name":"models/example","supportedGenerationMethods":["embedContent"]}', "headers": {}, "json": lambda self: {"name":"models/example", "supportedGenerationMethods":["embedContent"]}})()
        with patch("providers.requests.get", return_value=response):
            ok, reason = _validate_gemini_model("example", "test-key-abcdef")
        self.assertFalse(ok)
        self.assertIn("model_unsupported_generation", reason)

    def test_network_retries_once(self):
        response = type("Response", (), {"status_code": 200, "text": "{}", "headers": {}, "json": lambda self: {}})()
        with patch("providers.requests.post", side_effect=[requests.Timeout(), response]) as post:
            self.assertEqual(_post("https://example.invalid", {}, {}, 5), {})
        self.assertEqual(post.call_count, 2)

if __name__ == "__main__": unittest.main()
