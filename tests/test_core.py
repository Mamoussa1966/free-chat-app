import os
import unittest
from unittest.mock import patch

from providers import (
    SEATS,
    _classify,
    _sanitize,
    capture_model_candidates,
    get_model_candidates,
)


class CoreTests(unittest.TestCase):

    def test_five_core_seats(self):
        self.assertEqual(len(SEATS), 5)

        self.assertEqual(
            [seat.key for seat in SEATS],
            [
                "openai",
                "gemini",
                "claude",
                "grok",
                "kimi",
            ],
        )

    def test_seat_metadata_is_present(self):
        for seat in SEATS:
            self.assertTrue(seat.key)
            self.assertTrue(seat.label)
            self.assertTrue(seat.provider)

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
                403,
                "permission denied",
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

    def test_sanitize_removes_bearer_token(self):
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

    def test_sanitize_removes_common_secret_patterns(self):
        values = [
            "api_key=abcdefghijklmnopqrstuvwxyz",
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
            "token=abcdefghijklmnopqrstuvwxyz",
        ]

        for original in values:
            sanitized = _sanitize(original)

            self.assertNotEqual(
                sanitized,
                original,
            )

            self.assertIn(
                "REDACTED",
                sanitized,
            )

    def test_openai_env_override(self):
        with patch.dict(
            os.environ,
            {
                "OPENAI_MODELS": "gpt-test-a,gpt-test-b",
            },
            clear=False,
        ):
            self.assertEqual(
                get_model_candidates(SEATS[0]),
                (
                    "gpt-test-a",
                    "gpt-test-b",
                ),
            )

    def test_gemini_env_override(self):
        seat = next(
            seat
            for seat in SEATS
            if seat.key == "gemini"
        )

        with patch.dict(
            os.environ,
            {
                "GEMINI_MODELS": "gemini-test-a,gemini-test-b",
            },
            clear=False,
        ):
            self.assertEqual(
                get_model_candidates(seat),
                (
                    "gemini-test-a",
                    "gemini-test-b",
                ),
            )

    def test_claude_env_override(self):
        seat = next(
            seat
            for seat in SEATS
            if seat.key == "claude"
        )

        with patch.dict(
            os.environ,
            {
                "CLAUDE_MODELS": "claude-test-a,claude-test-b",
            },
            clear=False,
        ):
            self.assertEqual(
                get_model_candidates(seat),
                (
                    "claude-test-a",
                    "claude-test-b",
                ),
            )

    def test_grok_env_override(self):
        seat = next(
            seat
            for seat in SEATS
            if seat.key == "grok"
        )

        with patch.dict(
            os.environ,
            {
                "GROK_MODELS": "grok-test-a,grok-test-b",
            },
            clear=False,
        ):
            self.assertEqual(
                get_model_candidates(seat),
                (
                    "grok-test-a",
                    "grok-test-b",
                ),
            )

    def test_kimi_env_override(self):
        seat = next(
            seat
            for seat in SEATS
            if seat.key == "kimi"
        )

        with patch.dict(
            os.environ,
            {
                "KIMI_MODELS": "kimi-test-a,kimi-test-b",
            },
            clear=False,
        ):
            self.assertEqual(
                get_model_candidates(seat),
                (
                    "kimi-test-a",
                    "kimi-test-b",
                ),
            )

    def test_streamlit_secret_model_override(self):
        with patch(
            "providers._streamlit_secret",
            side_effect=lambda name: (
                "gpt-secret-a,gpt-secret-b"
                if name == "OPENAI_MODELS"
                else None
            ),
        ):
            self.assertEqual(
                get_model_candidates(SEATS[0]),
                (
                    "gpt-secret-a",
                    "gpt-secret-b",
                ),
            )

    def test_capture_model_candidates_returns_all_five_seats(self):
        with patch(
            "providers.get_model_candidates",
            side_effect=lambda seat: (
                f"{seat.key}-model-a",
                f"{seat.key}-model-b",
            ),
        ):
            snapshot = capture_model_candidates()

        self.assertEqual(
            set(snapshot.keys()),
            {
                "openai",
                "gemini",
                "claude",
                "grok",
                "kimi",
            },
        )

        for seat in SEATS:
            self.assertEqual(
                snapshot[seat.key],
                (
                    f"{seat.key}-model-a",
                    f"{seat.key}-model-b",
                ),
            )

    def test_capture_model_candidates_is_independent_snapshot(self):
        with patch(
            "providers.get_model_candidates",
            side_effect=lambda seat: (
                f"{seat.key}-model",
            ),
        ):
            snapshot = capture_model_candidates()

        self.assertIsInstance(
            snapshot,
            dict,
        )

        for seat in SEATS:
            self.assertIn(
                seat.key,
                snapshot,
            )

            self.assertIsInstance(
                snapshot[seat.key],
                tuple,
            )

    def test_model_candidates_are_non_empty_for_each_seat(self):
        for seat in SEATS:
            candidates = get_model_candidates(seat)

            self.assertIsInstance(
                candidates,
                tuple,
            )

            self.assertGreaterEqual(
                len(candidates),
                1,
            )

            for candidate in candidates:
                self.assertIsInstance(
                    candidate,
                    str,
                )

                self.assertTrue(
                    candidate.strip(),
                )

    def test_provider_keys_are_unique(self):
        keys = [
            seat.key
            for seat in SEATS
        ]

        self.assertEqual(
            len(keys),
            len(set(keys)),
        )

    def test_provider_labels_are_non_empty(self):
        for seat in SEATS:
            self.assertTrue(
                seat.label.strip()
            )

    def test_model_snapshot_contains_tuples(self):
        snapshot = capture_model_candidates()

        self.assertIsInstance(
            snapshot,
            dict,
        )

        for seat in SEATS:
            self.assertIn(
                seat.key,
                snapshot,
            )

            self.assertIsInstance(
                snapshot[seat.key],
                tuple,
            )


if __name__ == "__main__":
    unittest.main()
