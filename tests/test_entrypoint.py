import importlib
import sys
import types
import unittest


class EntryPointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fake = types.ModuleType("streamlit")
        fake.session_state = {}
        sys.modules.setdefault("streamlit", fake)

    def test_main_exposes_run_app(self):
        module = importlib.import_module("main")
        self.assertTrue(callable(getattr(module, "run_app", None)))


if __name__ == "__main__":
    unittest.main()
