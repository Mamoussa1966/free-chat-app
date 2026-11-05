import ast
import unittest
from pathlib import Path

class HardeningTests(unittest.TestCase):
    def test_all_python_sources_parse_and_compile(self):
        for path in Path(".").glob("*.py"):
            source = path.read_text(encoding="utf-8")
            ast.parse(source, filename=str(path))
            compile(source, str(path), "exec")
    def test_no_local_engine_or_paid_api_contract(self):
        source = Path("main.py").read_text(encoding="utf-8")
        providers = Path("providers.py").read_text(encoding="utf-8")
        self.assertNotIn("generate_local", source)
        self.assertNotIn("from local_engine import", source)
        self.assertIn("لا Local Engine ولا Paid fallback", source)
        self.assertIn("provider_zero_cost_policy_block_reason", source)
        self.assertIn("GEMINI_API_ZERO_COST_CONFIRMED", providers)
        self.assertIn("GEMINI_ZERO_COST_MODEL_ALLOWLIST", providers)
        self.assertIn("ZERO_COST_API_POLICY_BLOCKED", providers)
    def test_free_cap(self):
        source = Path("providers.py").read_text(encoding="utf-8")
        self.assertIn("MAX_MODELS_PER_SEAT = 10", source)
    def test_required_files_exist(self):
        for path in ("app.py", "main.py", "providers.py", "attachment_utils.py", "gitops_layer.py", "build_release.py", ".streamlit/secrets.toml.example"):
            self.assertTrue(Path(path).is_file(), path)

if __name__ == "__main__": unittest.main()
