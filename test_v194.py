import os
import sys
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from local_engine import generate_local
from main import AgentResult, run_agent, run_parallel, select_agents
from providers import PROVIDERS, ProviderError, _gemini_interaction_text, call_official, get_models, safe_error


class V194Tests(unittest.TestCase):
    def test_fifteen_seats(self):
        agents = select_agents(15)
        self.assertEqual(len(agents), 15)
        self.assertEqual(agents[-1]["id"], "compliance")
        self.assertEqual(select_agents(1)[0]["id"], "analysis")
        self.assertEqual(len(select_agents(99)), 15)

    def test_no_key_is_direct_local(self):
        agent = select_agents(5)[0]
        with patch("main.call_official", side_effect=AssertionError("network must not be called")):
            result = run_agent(agent, "كيف أبني نظاماً آمناً؟", "", "دقيقة", credential=None)
        self.assertTrue(result.success)
        self.assertEqual(result.mode, "local_direct")
        self.assertFalse(result.fallback_used)
        self.assertFalse(result.provider_attempted)
        self.assertFalse(result.official_authenticated)

    def test_official_success_is_truthful(self):
        agent = select_agents(5)[0]
        with patch("main.call_official", return_value="official response"):
            result = run_agent(agent, "hello", "", "ودية", credential="TEST_KEY")
        self.assertTrue(result.success)
        self.assertEqual(result.mode, "official_api")
        self.assertTrue(result.official_authenticated)
        self.assertTrue(result.provider_attempted)
        self.assertFalse(result.fallback_used)

    def test_official_failure_isolated_to_local_fallback(self):
        agent = select_agents(5)[0]
        with patch("main.call_official", side_effect=ProviderError("HTTP 429: rate limit")):
            result = run_agent(agent, "hello", "", "ودية", credential="TEST_KEY")
        self.assertTrue(result.success)
        self.assertEqual(result.mode, "local_fallback")
        self.assertTrue(result.fallback_used)
        self.assertTrue(result.provider_attempted)
        self.assertFalse(result.official_authenticated)

    def test_no_credential_does_not_call_network(self):
        with patch("providers._post", side_effect=AssertionError("network called")):
            with self.assertRaises(ProviderError):
                call_official("openai", "hello", get_models(PROVIDERS["openai"])[0], 5, credential="")

    def test_worker_uses_supplied_credential(self):
        captured = {}
        def fake_post(url, headers, payload, timeout, retries=1):
            captured["auth"] = headers.get("Authorization")
            return {"output_text": "official response"}
        with patch("providers._streamlit_secret", side_effect=AssertionError("worker touched Streamlit secrets")):
            with patch("providers._post", side_effect=fake_post):
                text = call_official("openai", "hello", get_models(PROVIDERS["openai"])[0], 5, credential="TEST_KEY")
        self.assertEqual(text, "official response")
        self.assertEqual(captured["auth"], "Bearer TEST_KEY")

    def test_gemini_parser(self):
        data = {"output": [{"type": "text", "text": "hello"}]}
        self.assertEqual(_gemini_interaction_text(data), "hello")
        data2 = {"steps": [{"type": "model_output", "content": [{"type": "text", "text": "hello2"}]}]}
        self.assertEqual(_gemini_interaction_text(data2), "hello2")

    def test_secret_redaction(self):
        msg = safe_error(Exception("Authorization: Bearer SECRET123 api_key=SECRET456"))
        self.assertNotIn("SECRET123", msg)
        self.assertNotIn("SECRET456", msg)
        self.assertIn("REDACTED", msg)

    def test_local_engine_is_truthful_and_dynamic(self):
        a = generate_local("analysis", "التحليل", "حلل", "كيف أبني قاعدة بيانات آمنة؟")
        b = generate_local("risk", "المخاطر", "راجع", "كيف أخطط لرحلة تعليمية؟")
        self.assertNotEqual(a, b)
        self.assertIn("قاعدة بيانات", a)
        self.assertIn("رحلة", b)
        self.assertIn("Local Engine", a)
        self.assertNotIn("أنا ChatGPT", a)
        self.assertNotIn("أنا Gemini", b)

    def test_parallel_fault_isolation(self):
        agents = select_agents(5)
        creds = {a["provider"]: "KEY" for a in agents}
        def fake_run(agent, *args, **kwargs):
            if agent["id"] == "critic":
                raise RuntimeError("boom")
            return AgentResult(agent["id"], agent["name"], agent["role"], agent["provider"], "ok", True, 0.01, "local_direct", "local-engine", "", False, "local_direct", False, False)
        with patch("main.run_agent", side_effect=fake_run):
            results = run_parallel(agents, "hello", [], "دقيقة", creds)
        self.assertEqual(len(results), 5)
        self.assertTrue(any(r.agent_id == "critic" and r.mode == "error" for r in results))
        self.assertEqual(sum(r.success for r in results), 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
