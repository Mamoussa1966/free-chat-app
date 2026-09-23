import os
import sys
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from providers import MAX_MODELS_PER_SEAT, SEATS, _parse_models, get_model_candidates


class GeminiFreeModelsRegressionTests(unittest.TestCase):
    def setUp(self):
        self.gemini = next(seat for seat in SEATS if seat.key == "gemini")

    def test_streamlit_secret_is_live_source_and_changes_are_reflected(self):
        """Regression: changing Streamlit GEMINI_FREE_MODELS must change the loaded cascade."""
        with patch("providers._streamlit_secret", side_effect=lambda name: {
            "GEMINI_FREE_MODELS": "model-A,model-B"
        }.get(name)):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("GEMINI_FREE_MODELS", None)
                first = get_model_candidates(self.gemini)

        with patch("providers._streamlit_secret", side_effect=lambda name: {
            "GEMINI_FREE_MODELS": "model-C,model-D,model-E"
        }.get(name)):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("GEMINI_FREE_MODELS", None)
                second = get_model_candidates(self.gemini)

        self.assertEqual(first, ("model-A", "model-B"))
        self.assertEqual(second, ("model-C", "model-D", "model-E"))
        self.assertNotEqual(first, second)

    def test_no_secret_means_no_implicit_gemini_model(self):
        """Regression: an empty secret must never resurrect hidden/default Gemini models."""
        with patch("providers._streamlit_secret", return_value=None):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("GEMINI_FREE_MODELS", None)
                self.assertEqual(get_model_candidates(self.gemini), ())

    def test_typographic_comma_does_not_become_a_silent_second_model(self):
        """Regression: U+201A comma must not create a hidden/garbled model ID."""
        with patch("providers._streamlit_secret", return_value="model-A‚model-B"):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("GEMINI_FREE_MODELS", None)
                self.assertEqual(get_model_candidates(self.gemini), ())

    def test_free_model_list_is_hard_bounded_to_ten(self):
        raw = ",".join(f"model-{i}" for i in range(1, 16))
        with patch("providers._streamlit_secret", return_value=raw):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("GEMINI_FREE_MODELS", None)
                models = get_model_candidates(self.gemini)
        self.assertEqual(len(models), MAX_MODELS_PER_SEAT)
        self.assertEqual(models[0], "model-1")
        self.assertEqual(models[-1], "model-10")

    def test_parser_rejects_unsafe_model_tokens_instead_of_repairing_them(self):
        self.assertEqual(_parse_models("model-A‚model-B"), ())
        self.assertEqual(_parse_models("model-A model-B"), ())


if __name__ == "__main__":
    unittest.main()
