import importlib.util
import unittest

class EntryPointTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("streamlit"), "streamlit dependency not installed in validation environment")
    def test_main_exposes_run_app(self):
        from main import run_app
        self.assertTrue(callable(run_app))

if __name__ == "__main__": unittest.main()
