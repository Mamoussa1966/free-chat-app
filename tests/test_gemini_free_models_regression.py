import os
import unittest
from unittest.mock import patch

from providers import MAX_MODELS_PER_SEAT, SEATS, _parse_models, get_model_candidates


class GeminiFreeModelsRegressionTests(unittest.TestCase):
    def setUp(self):
        self.gemini = next(seat for seat in SEATS if seat.key == "gemini")

    def test_streamlit_secret_is_live_source_and_changes_are_reflected(self):
        with patch("providers._read_setting", side_effect=lambda name: (
            ("model-A,model-B", "streamlit_secrets") if name == "GEMINI_FREE_MODELS" else (None, "missing")
        )):
            first = get_model_candidates(self.gemini)
        with patch("providers._read_setting", side_effect=lambda name: (
            ("model-C,model-D,model-E", "streamlit_secrets") if name == "GEMINI_FREE_MODELS" else (None, "missing")
        )):
            second = get_model_candidates(self.gemini)
        self.assertEqual(first, ("model-A", "model-B"))
        self.assertEqual(second, ("model-C", "model-D", "model-E"))
        self.assertNotEqual(first, second)

    def test_no_secret_means_no_implicit_gemini_model(self):
        with patch("providers._read_setting", return_value=(None, "missing")):
            self.assertEqual(get_model_candidates(self.gemini), ())

    def test_typographic_comma_does_not_become_a_silent_second_model(self):
        with patch("providers._read_setting", return_value=("model-A‚model-B", "streamlit_secrets")):
            self.assertEqual(get_model_candidates(self.gemini), ())

    def test_free_model_list_is_hard_bounded_to_ten(self):
        raw = ",".join(f"model-{i}" for i in range(1, 16))
        with patch("providers._read_setting", return_value=(raw, "streamlit_secrets")):
            models = get_model_candidates(self.gemini)
        self.assertEqual(len(models), MAX_MODELS_PER_SEAT)
        self.assertEqual(models[0], "model-1")
        self.assertEqual(models[-1], "model-10")

    def test_parser_rejects_unsafe_model_tokens_instead_of_repairing_them(self):
        self.assertEqual(_parse_models("model-A‚model-B"), ())
        self.assertEqual(_parse_models("model-A model-B"), ())


if __name__ == "__main__":
    unittest.main()
