import os
import sys
import types
import unittest
from unittest.mock import patch

# The provider module imports Streamlit lazily, but a minimal fake keeps this
# regression test runnable in environments where Streamlit is not installed.
if "streamlit" not in sys.modules:
    fake = types.ModuleType("streamlit")
    fake.secrets = {}
    sys.modules["streamlit"] = fake

from providers import SEATS, get_model_candidates, get_model_config_diagnostic


class FreeModelsSecretAuthorityTests(unittest.TestCase):
    def test_gemini_free_secret_is_authoritative(self):
        gemini = next(s for s in SEATS if s.key == "gemini")
        fake_secrets = {"GEMINI_FREE_MODELS": "gemini-test-a,gemini-test-b"}
        with patch("providers._streamlit_secret", side_effect=lambda name: fake_secrets.get(name)), \
             patch.dict(os.environ, {"GEMINI_FREE_MODELS": "stale-env-model"}, clear=False):
            self.assertEqual(
                get_model_candidates(gemini),
                ("gemini-test-a", "gemini-test-b"),
            )

    def test_no_free_secret_means_no_implicit_default(self):
        gemini = next(s for s in SEATS if s.key == "gemini")
        with patch("providers._streamlit_secret", return_value=None), \
             patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_FREE_MODELS", None)
            self.assertEqual(get_model_candidates(gemini), ())

    def test_unicode_comma_does_not_silently_select_a_model(self):
        gemini = next(s for s in SEATS if s.key == "gemini")
        bad = "gemini-3.1-pro-preview‚gemini-3.5-flash"
        with patch("providers._streamlit_secret", side_effect=lambda name: bad if name == "GEMINI_FREE_MODELS" else None):
            self.assertEqual(get_model_candidates(gemini), ())
            diagnostic = get_model_config_diagnostic(gemini)
            self.assertTrue(diagnostic["invalid"])


if __name__ == "__main__":
    unittest.main()
