import unittest
from unittest.mock import patch

from providers import MAX_RESPONSE_BODY_CHARS, MAX_RESPONSE_CHARS, ProviderError, SEATS, _post, _prompt, call_official


class ProviderRuntimeTests(unittest.TestCase):
    def test_prompt_has_one_current_request_marker(self):
        text = _prompt("Hello", "CTX", 1)
        self.assertEqual(text.count("CURRENT USER REQUEST:"), 1)
        self.assertIn("UNTRUSTED SHARED CONTEXT", text)

    def test_billing_429_is_not_retried(self):
        response = type("Response", (), {"status_code": 429, "text": '{"error":"credit balance exhausted"}', "headers": {}, "json": lambda self: {}})()
        with patch("providers.requests.post", return_value=response) as post:
            with self.assertRaises(ProviderError):
                _post("https://example.invalid", {}, {}, 5)
        self.assertEqual(post.call_count, 1)

    def test_deadline_prevents_provider_call_when_expired(self):
        with self.assertRaises(ProviderError) as ctx:
            _post("https://example.invalid", {}, {}, 5, deadline=__import__("time").monotonic() - 1)
        self.assertEqual(ctx.exception.error_class, "deadline_exceeded")

    def test_response_text_is_bounded(self):
        from unittest.mock import patch
        huge = "x" * (MAX_RESPONSE_CHARS + 100)
        fake = {"output_text": huge}
        with patch("providers._post", return_value=fake):
            text = call_official(SEATS[0], "hello", "model", "key", 5, [])
        self.assertLessEqual(len(text), MAX_RESPONSE_CHARS + 40)
        self.assertIn("response truncated by safety cap", text)

    def test_response_body_cap_is_enforced(self):
        huge = "x" * (MAX_RESPONSE_BODY_CHARS + 1)
        response = type("Response", (), {"status_code": 200, "text": huge, "headers": {}, "json": lambda self: {}})()
        with patch("providers.requests.post", return_value=response):
            with self.assertRaises(ProviderError) as ctx:
                _post("https://example.invalid", {}, {}, 5)
        self.assertEqual(ctx.exception.error_class, "response_too_large")

    def test_invalid_endpoint_is_rejected_before_network(self):
        with patch("providers.requests.post") as post:
            with self.assertRaises(ProviderError) as ctx:
                _post("http://example.invalid", {}, {}, 5)
        self.assertEqual(ctx.exception.error_class, "configuration")
        post.assert_not_called()

    def test_network_error_gets_one_retry(self):
        import requests
        response = type("Response", (), {"status_code": 200, "text": "{}", "headers": {}, "json": lambda self: {}})()
        with patch("providers.requests.post", side_effect=[requests.Timeout(), response]) as post:
            result = _post("https://example.invalid", {}, {}, 5)
        self.assertEqual(result, {})
        self.assertEqual(post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
