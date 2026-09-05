import os
import unittest
from unittest.mock import patch
from local_engine import generate_local
# The production UI dependency is intentionally not required for provider/local unit tests.
import sys, types
_fake_st = types.SimpleNamespace(secrets={}, session_state={})
sys.modules.setdefault("streamlit", _fake_st)
from main import AgentResult, audit_record, export_json, run_agent
from providers import PROVIDERS, call_official, get_models, safe_error
class FakeResponse:
    def __init__(self, data, status_code=200, text=""):
        self._data = data
        self.status_code = status_code
        self.text = text
    def json(self):
        return self._data
class CoreTests(unittest.TestCase):
    def test_local_engine_is_truthful(self):
        text = generate_local("analysis", "التحليل", "حلل", "test")
        self.assertIn("Local Engine", text)
        self.assertNotIn("هذه النتيجة من ChatGPT", text)
    def test_defaults(self):
        self.assertEqual(PROVIDERS["gemini"].default_models[0], "gemini-3.8-flash")
        self.assertEqual(PROVIDERS["xai"].default_models[0], "grok-4.6")
        self.assertEqual(PROVIDERS["kimi"].default_models[0], "kimi-k3")
        self.assertEqual(PROVIDERS["anthropic"].default_models[0], "claude-sonnet-5")
    def test_safe_error_redacts_secret(self):
        value = safe_error(Exception("Authorization: Bearer SECRET"))
        self.assertNotIn("SECRET", value)
        self.assertIn("REDACTED", value)
    def test_model_override(self):
        with patch.dict(os.environ, {"XAI_MODELS": "one,two"}, clear=False):
            self.assertEqual(get_models(PROVIDERS["xai"]), ("one", "two"))
    def test_no_key_means_no_network(self):
        agent = {"id": "analysis", "provider": "openai", "name": "ChatGPT", "role": "analysis", "icon": "", "instruction": "analyze"}
        with patch.dict(os.environ, {}, clear=True):
            with patch("providers.requests.post") as post:
                result = run_agent(agent, "hello", "", "direct")
        post.assert_not_called()
        self.assertTrue(result.success)
        self.assertEqual(result.mode, "local-fallback")
        self.assertFalse(result.official_authenticated)
        self.assertTrue(result.fallback_used)
    def test_official_openai_success(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "TEST"}, clear=True):
            with patch("providers.requests.post", return_value=FakeResponse({"output_text": "official-ok"})):
                text = call_official("openai", "hello", "gpt-5.6-luna", 5)
        self.assertEqual(text, "official-ok")
    def test_official_failure_falls_back(self):
        agent = {"id": "analysis", "provider": "openai", "name": "ChatGPT", "role": "analysis", "icon": "", "instruction": "analyze"}
        with patch.dict(os.environ, {"OPENAI_API_KEY": "TEST"}, clear=True):
            with patch("providers.requests.post", side_effect=RuntimeError("boom")):
                result = run_agent(agent, "hello", "", "direct")
        self.assertTrue(result.success)
        self.assertEqual(result.mode, "local-fallback")
        self.assertTrue(result.fallback_used)
        self.assertFalse(result.official_authenticated)
    def test_audit_identity(self):
        local = AgentResult("x", "X", "role", "openai", "local", True, 0.1, "local", "local-engine")
        audit = audit_record(local)
        self.assertFalse(audit["official_authenticated"])
        self.assertTrue(audit["local_engine"])
        self.assertIsNone(audit["model_id"])
    def test_json_contains_explicit_source_metadata(self):
        local = AgentResult("x", "X", "role", "openai", "local", True, 0.1, "local", "local-engine")
        data = export_json("q", [local], None, "run1")
        self.assertIn('"official_authenticated": false', data)
        self.assertIn('"source_mode": "local"', data)
        self.assertIn('"identity_policy"', data)
if __name__ == "__main__":
    unittest.main()
