import unittest
from unittest.mock import patch

from providers import ProviderError, SEATS, _post, _prompt, call_seat


class ProviderRuntimeTests(unittest.TestCase):
    def test_prompt_has_no_duplicate_attachment_suffix(self):
        text = _prompt("Hello", "CTX", 1)
        self.assertEqual(text.count("CURRENT USER REQUEST:"), 1)
        self.assertNotIn("attachment_note", text)

    def test_billing_429_is_not_retried_inside_same_http_attempt(self):
        response = type("Response", (), {
            "status_code": 429,
            "text": '{"error":"credit balance exhausted"}',
            "headers": {},
            "json": lambda self: {},
        })()
        with patch("providers.requests.post", return_value=response) as post:
            with self.assertRaises(ProviderError):
                _post("https://example.invalid", {}, {}, 5)
        self.assertEqual(post.call_count, 1)

    def test_free_cascade_tries_next_model_after_quota_failure(self):
        seat = SEATS[0]
        errors = [
            ProviderError("quota", 429, "rate_limit_or_quota"),
            ProviderError("invalid model", 404, "model_not_found_or_invalid"),
        ]

        def fake_call(*args, **kwargs):
            if errors:
                raise errors.pop(0)
            return "FREE_OK"

        models = ("free-1", "free-2", "free-3")
        with patch("providers.call_official", side_effect=fake_call):
            result = call_seat(seat, "Hello", "", 1, False, "fake-key", [], models)

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["mode"], "official")
        self.assertEqual(result["model"], "free-3")
        self.assertEqual(result["attempted_models"], ["free-1", "free-2", "free-3"])
        self.assertTrue(result["official_authenticated"])

    def test_no_free_models_never_uses_local_engine(self):
        seat = SEATS[0]
        with patch("providers.call_official") as call:
            result = call_seat(seat, "Hello", "", 1, False, "fake-key", [], ())
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["mode"], "official")
        self.assertEqual(result["error"].split(";", 1)[0], "class=no_free_models_configured")
        call.assert_not_called()


    def test_openai_diagnostic_authenticates_without_free_model(self):
        from providers import diagnostic_seat
        response = type("Response", (), {
            "status_code": 200,
            "text": '{"object":"list","data":[]}',
            "headers": {},
            "json": lambda self: {"object": "list", "data": []},
        })()
        with patch("providers.requests.get", return_value=response) as get:
            result = diagnostic_seat(SEATS[0], "fake-key", ())
        get.assert_called_once()
        self.assertEqual(result["status"], "AUTHENTICATED_NO_FREE_MODEL")
        self.assertTrue(result["official_authenticated"])
        self.assertIn("openai_authenticated_but_no_free_model", result["error"])

    def test_openai_diagnostic_classifies_401(self):
        from providers import diagnostic_seat
        response = type("Response", (), {
            "status_code": 401,
            "text": '{"error":{"message":"invalid api key"}}',
            "headers": {},
            "json": lambda self: {},
        })()
        with patch("providers.requests.get", return_value=response):
            result = diagnostic_seat(SEATS[0], "bad-key", ())
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("class=openai_authentication_failed", result["error"])
        self.assertFalse(result["official_authenticated"])

    def test_openai_diagnostic_classifies_billing_429(self):
        from providers import diagnostic_seat
        response = type("Response", (), {
            "status_code": 429,
            "text": '{"error":{"code":"credit_balance_exhausted"}}',
            "headers": {},
            "json": lambda self: {},
        })()
        with patch("providers.requests.get", return_value=response):
            result = diagnostic_seat(SEATS[0], "key", ())
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("class=openai_credit_or_billing_exhausted", result["error"])



if __name__ == "__main__":
    unittest.main()
