import unittest
from unittest.mock import patch

from providers import ProviderError, SEATS, _post, _prompt, call_seat


class ProviderRuntimeTests(unittest.TestCase):
    def test_prompt_has_no_duplicate_attachment_suffix(self):
        text = _prompt("Hello", "CTX", 1)
        self.assertEqual(text.count("CURRENT USER REQUEST:"), 1)
        self.assertNotIn("attachment_note", text)

    def test_billing_429_is_not_retried(self):
        response = type(
            "Response",
            (),
            {
                "status_code": 429,
                "text": '{"error":"credit balance exhausted"}',
                "json": lambda self: {},
            },
        )()

        with patch(
            "providers.requests.post",
            return_value=response,
        ) as post:
            with self.assertRaises(ProviderError):
                _post(
                    "https://example.invalid",
                    {},
                    {},
                    5,
                )

        self.assertEqual(post.call_count, 1)

    def test_local_result_preserves_official_failure_reason(self):
        seat = SEATS[0]

        with patch(
            "providers.call_official",
            side_effect=ProviderError(
                "HTTP 429: credit balance exhausted",
                429,
                "rate_limit_or_quota",
            ),
        ):
            result = call_seat(
                seat,
                "Hello",
                "",
                1,
                True,
                "fake-key",
                [],
                (seat.default_model,),
            )

        self.assertEqual(result["status"], "LOCAL")
        self.assertEqual(result["mode"], "local")
        self.assertIn(
            "credit balance exhausted",
            result["error"],
        )
        self.assertFalse(
            result["official_authenticated"]
        )


if __name__ == "__main__":
    unittest.main()
