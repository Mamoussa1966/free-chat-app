import os
import unittest
from unittest.mock import patch

from providers import SEATS, _classify, _sanitize, get_model_candidates


class CoreTests(unittest.TestCase):
    def test_twenty_provider_seats(self):
        self.assertEqual(len(SEATS), 20)
        self.assertEqual(
            [s.key for s in SEATS],
            ["openai", "gemini", "anthropic", "groq", "openrouter", "cohere",
             "mistral", "xai", "deepseek", "together", "perplexity", "fireworks",
             "replicate", "huggingface", "ai21", "kimi", "dashscope", "zhipu",
             "deepinfra", "anyscale"],
        )

    def test_error_classification(self):
        self.assertEqual(_classify(401, "invalid api key"), "authentication_failed")
        self.assertEqual(_classify(429, "quota exceeded"), "billing_or_quota")
        self.assertEqual(_classify(404, "model not found"), "model_not_found_or_invalid")
        self.assertEqual(_classify(403, "access denied"), "permission_denied")

    def test_sanitize(self):
        value = _sanitize("Authorization: Bearer sk-abcdefghijklmnop")
        self.assertNotIn("abcdefghijklmnop", value)
        self.assertIn("REDACTED", value)

    def test_free_model_env_override_accepts_ten(self):
        models = ",".join(f"free-{i}" for i in range(1, 11))
        with patch.dict(os.environ, {"OPENAI_FREE_MODELS": models}, clear=False):
            self.assertEqual(len(get_model_candidates(SEATS[0])), 10)
            self.assertEqual(get_model_candidates(SEATS[0])[0], "free-1")
            self.assertEqual(get_model_candidates(SEATS[0])[-1], "free-10")

    def test_streamlit_secret_free_model_override(self):
        with patch(
            "providers._streamlit_secret",
            side_effect=lambda name: "free-a,free-b"
            if name == "OPENAI_FREE_MODELS"
            else None,
        ):
            self.assertEqual(
                get_model_candidates(SEATS[0]),
                ("free-a", "free-b"),
            )

    def test_model_parser_rejects_unsafe_values(self):
        from providers import _parse_models

        self.assertEqual(
            _parse_models(
                "good-model, bad model, bad@model,good-model"
            ),
            ("good-model",),
        )

    def test_no_implicit_free_model_defaults(self):
        for seat in SEATS:
            self.assertEqual(get_model_candidates(seat), ())
            self.assertEqual(seat.default_model, "")
            self.assertEqual(seat.fallback_models, ())

    def test_seat_contract_fields_are_well_formed(self):
        for seat in SEATS:
            self.assertTrue(seat.kind)
            self.assertTrue(seat.endpoint)
            self.assertTrue(seat.env_names)
            self.assertTrue(seat.model_env)
            self.assertTrue(seat.name)
            self.assertTrue(seat.label)


if __name__ == "__main__":
    unittest.main()
