import ast
import unittest


class HardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("main.py", encoding="utf-8") as f:
            cls.main_source = f.read()
        with open("providers.py", encoding="utf-8") as f:
            cls.provider_source = f.read()

    def test_all_python_sources_parse(self):
        for path in ("app.py", "main.py", "providers.py", "attachment_utils.py"):
            with open(path, encoding="utf-8") as f:
                ast.parse(f.read(), filename=path)

    def test_no_local_engine_import_or_fallback(self):
        self.assertNotIn("from local_engine import", self.main_source)
        self.assertNotIn("generate_local", self.main_source)
        self.assertNotIn("local_fallback", self.main_source)

    def test_free_cascade_cap_is_ten(self):
        self.assertIn("MAX_MODELS_PER_SEAT = 10", self.provider_source)
        self.assertIn("Free Cascade #1→#10", self.main_source)

    def test_current_user_is_excluded_from_history(self):
        self.assertIn("exclude_message_id", self.main_source)
        self.assertIn("item.get(\"id\") == exclude_message_id", self.main_source)

    def test_credentials_are_captured_before_threads(self):
        self.assertIn("credentials = capture_credentials()", self.main_source)
        self.assertIn("model_candidates = capture_model_candidates()", self.main_source)

    def test_no_hardcoded_paid_model_defaults(self):
        self.assertIn('model_env=("OPENAI_FREE_MODELS",)', self.provider_source)
        self.assertIn('model_env=("ANTHROPIC_FREE_MODELS", "CLAUDE_FREE_MODELS")', self.provider_source)
        self.assertIn('model_env=("XAI_FREE_MODELS", "GROK_FREE_MODELS")', self.provider_source)


if __name__ == "__main__":
    unittest.main()
