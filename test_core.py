import os
import sys
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from local_engine import generate_local
from providers import PROVIDERS, call_official, get_models, safe_error


class FakeResponse:
    status_code = 200
    text = ""
    def json(self):
        return {"output_text": "official ok"}


class CoreTests(unittest.TestCase):
    def test_provider_registry(self):
        self.assertEqual(set(PROVIDERS), {"openai", "gemini", "anthropic", "xai", "kimi"})
        for cfg in PROVIDERS.values():
            self.assertTrue(cfg.endpoint.startswith("https://"))
            self.assertTrue(cfg.default_models)

    def test_local_engine_is_explicitly_local(self):
        text = generate_local("analysis", "التحليل", "حلل", "اختبار معماري")
        self.assertIn("Local Engine", text)
        self.assertNotIn("مصدر هذه النتيجة: ChatGPT", text)

    def test_error_redaction(self):
        text = safe_error(Exception("Authorization: Bearer SECRET123"))
        self.assertNotIn("SECRET123", text)
        self.assertIn("REDACTED", text)

    def test_official_call_uses_supplied_credential(self):
        captured = {}
        def fake_post(url, headers, payload, timeout, retries=1):
            captured["headers"] = headers
            return {"output_text": "official ok"}
        with patch("providers._post", side_effect=fake_post):
            out = call_official("openai", "hello", get_models(PROVIDERS["openai"])[0], 5, credential="TEST_SECRET")
        self.assertEqual(out, "official ok")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer TEST_SECRET")

    def test_no_credential_makes_no_network_call(self):
        with patch("providers._post", side_effect=AssertionError("network must not be called")):
            with self.assertRaises(Exception):
                call_official("openai", "hello", get_models(PROVIDERS["openai"])[0], 5, credential=None)

    def test_v19_source_contracts(self):
        main_path = os.path.join(ROOT, "main.py")
        source = open(main_path, encoding="utf-8").read()
        self.assertIn('"15"', source)
        self.assertIn('"compliance"', source)
        self.assertIn("active_credentials", source)
        self.assertIn("credential=key", source)
        self.assertIn("st.markdown(r.text)", source)
        self.assertNotIn('html.escape(r.text).replace(chr(10), "<br>")', source)
        self.assertNotIn("if st.session_state.last_results and not query:", source)


if __name__ == "__main__":
    unittest.main()
