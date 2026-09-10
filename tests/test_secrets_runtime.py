import unittest
from unittest.mock import patch

from providers import SEATS, get_model_candidates, model_config_sources


class SecretsRuntimeTests(unittest.TestCase):
    def test_streamlit_secret_is_authoritative_for_free_models(self):
        with patch(
            "providers._read_setting",
            side_effect=lambda name: (
                ("gemini-secret-1‚gemini-secret-2", "streamlit_secrets")
                if name == "GEMINI_FREE_MODELS"
                else ("environment-model", "environment")
                if name == "GEMINI_MODELS"
                else (None, "missing")
            ),
        ):
            self.assertEqual(
                get_model_candidates(SEATS[1]),
                ("gemini-secret-1", "gemini-secret-2"),
            )
            self.assertEqual(model_config_sources()["gemini"], "streamlit_secrets")

    def test_free_models_never_fall_back_to_legacy_gemini_models(self):
        with patch(
            "providers._read_setting",
            side_effect=lambda name: (
                ("legacy-model", "environment")
                if name == "GEMINI_MODELS"
                else (None, "missing")
            ),
        ):
            self.assertEqual(get_model_candidates(SEATS[1]), ())


    def test_empty_streamlit_secret_blocks_stale_environment(self):
        with patch(
            "providers._read_setting",
            side_effect=lambda name: (
                (None, "streamlit_secrets_empty")
                if name == "GEMINI_FREE_MODELS"
                else ("stale-env-model", "environment")
                if name == "GEMINI_MODELS"
                else (None, "missing")
            ),
        ):
            self.assertEqual(get_model_candidates(SEATS[1]), ())

    def test_unicode_separator_does_not_merge_model_ids(self):
        with patch(
            "providers._read_setting",
            side_effect=lambda name: (
                ("gemini-a‚gemini-b،gemini-c，gemini-d؛gemini-e", "streamlit_secrets")
                if name == "GEMINI_FREE_MODELS"
                else (None, "missing")
            ),
        ):
            self.assertEqual(
                get_model_candidates(SEATS[1]),
                ("gemini-a", "gemini-b", "gemini-c", "gemini-d", "gemini-e"),
            )


if __name__ == "__main__":
    unittest.main()
