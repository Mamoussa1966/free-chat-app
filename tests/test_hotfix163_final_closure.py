import os
import unittest
from unittest.mock import patch

from providers import _read_setting


class Hotfix163FinalClosureTests(unittest.TestCase):
    def test_read_setting_never_bypasses_streamlit_secret_seam(self):
        """A simulated absent Secret must not be bypassed by a live Secret lookup."""
        with patch("providers._streamlit_secret", return_value=None), patch(
            "providers._streamlit_secret_state",
            return_value=(True, "live-but-unreachable-model"),
        ), patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_FREE_MODELS", None)
            self.assertEqual(_read_setting("GEMINI_FREE_MODELS"), (None, "missing"))

    def test_empty_secret_blocks_environment_at_canonical_read_boundary(self):
        """An explicitly empty Streamlit Secret remains authoritative over ENV."""
        with patch("providers._streamlit_secret", return_value=""), patch.dict(
            os.environ, {"GEMINI_FREE_MODELS": "stale-env-model"}, clear=False
        ):
            self.assertEqual(
                _read_setting("GEMINI_FREE_MODELS"),
                ("", "streamlit_secrets_empty"),
            )


if __name__ == "__main__":
    unittest.main()
