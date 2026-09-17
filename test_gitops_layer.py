import unittest
import tempfile
from pathlib import Path
import gitops_layer as g

class GitOpsTests(unittest.TestCase):
    def setUp(self):
        g.ApprovalSystem.clear()
    def test_paths(self):
        self.assertEqual(g.CodeValidator.normalize_path("main.py"), "main.py")
        for value in ("../main.py", "/etc/passwd", r"C:\\main.py", "./main.py", "main.py\x00evil"):
            with self.assertRaises(ValueError): g.CodeValidator.normalize_path(value)
    def test_protected_paths(self):
        self.assertFalse(g.CodeValidator.is_protected_path("main.py"))
        self.assertTrue(g.CodeValidator.is_protected_path(".streamlit/secrets.toml"))
        self.assertTrue(g.CodeValidator.is_protected_path("unknown.py"))
    def test_ast_policy(self):
        for code in ("exec('x')", "eval('x')", "import subprocess", "import socket", "import os\nos.system('x')"):
            self.assertFalse(g.CodeValidator.audit_patch_ast_policy(code)["pass"])
    def test_hashes(self):
        self.assertNotEqual(g.DiffEngine.calculate_code_hash("x\n"), g.DiffEngine.calculate_code_hash("y\n"))
    def test_candidate_gate(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "main.py").write_text("x = 1\n", encoding="utf-8")
            result = g.TestGate.run_candidate_tests("x = 2\n", "main.py", "def test_candidate():\n    assert True\n", d)
            self.assertTrue(result["pass"])

if __name__ == "__main__": unittest.main()
