import unittest

class V216CompatibilityTests(unittest.TestCase):
    def test_project_has_no_local_engine_contract(self):
        with open("main.py", encoding="utf-8") as f:
            source = f.read()
        self.assertNotIn("generate_local", source)
        self.assertNotIn("from local_engine import", source)

    def test_zero_cost_api_contract_is_visible(self):
        with open("main.py", encoding="utf-8") as f:
            source = f.read()
        with open("providers.py", encoding="utf-8") as f:
            providers = f.read()
        self.assertIn("Gemini Free Tier", source)
        self.assertIn("Cloudflare Workers AI Free", source)
        self.assertIn("لا Local Engine ولا Paid fallback", source)
        self.assertIn("provider_zero_cost_policy_block_reason", source)
        self.assertIn("GEMINI_API_ZERO_COST_CONFIRMED", providers)
        self.assertIn("GEMINI_ZERO_COST_MODEL_ALLOWLIST", providers)
        self.assertIn("CLOUDFLARE_WORKERS_FREE_PLAN_CONFIRMED", providers)
        self.assertIn("CLOUDFLARE_WORKERS_AI_MODEL_ALLOWLIST", providers)

if __name__ == "__main__": unittest.main()
