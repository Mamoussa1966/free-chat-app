import unittest

class V216CompatibilityTests(unittest.TestCase):
    def test_project_has_no_local_engine_contract(self):
        with open("main.py", encoding="utf-8") as f:
            source = f.read()
        self.assertNotIn("generate_local", source)
        self.assertNotIn("from local_engine import", source)
    def test_free_only_contract_is_visible(self):
        with open("main.py", encoding="utf-8") as f:
            source = f.read()
        self.assertIn("Free API Cascade", source)
        self.assertIn("Free #1", source)
        self.assertIn("Free #10", source)

if __name__ == "__main__": unittest.main()
