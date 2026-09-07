import os
import unittest
from unittest.mock import patch

from providers import (
    SEATS,
    _classify,
    _sanitize,
    get_model_candidates,
)


class CoreTests(unittest.TestCase):

    def test_five_core_seats(self):
        self.assertEqual(
            len(SEATS),
            5,
        )

        self.assertEqual(
            [s.key for s in SEATS],
            [
                "openai",
                "gemini",
                "claude",
                "grok",
                "kimi",
            ],
        )

    def test_error_classification(self):
        self.assertEqual(
            _classify(
                401,
                "invalid api key",
            ),
            "authentication_or_permission",
        )

        self.assertEqual(
            _classify(
                429,
                "quota exceeded",
            ),
            "rate_limit_or_quota",
        )

        self.assertEqual(
            _classify(
                404,
                "model not found",
            ),
            "model_not_found_or_invalid",
        )

    def test_sanitize(self):
        value = _sanitize(
            "Authorization: "
            "Bearer sk-abcdefghijklmnop"
        )

        self.assertNotIn(
            "abcdefghijklmnop",
            value,
        )

        self.assertIn(
            "REDACTED",
            value,
        )

    def test_openai_override(self):
        with patch.dict(
            os.environ,
            {
                "OPENAI_MODELS":
                    "gpt-test-a,gpt-test-b"
            },
            clear=False,
        ):
            self.assertEqual(
                get_model_candidates(
                    SEATS[0]
                ),
                (
                    "gpt-test-a",
                    "gpt-test-b",
                ),
            )


if __name__ == "__main__":
    unittest.main()
