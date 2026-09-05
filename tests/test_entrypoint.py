import os
import sys
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class EntrypointTests(unittest.TestCase):
    def test_app_exports_main_from_application(self):
        import app
        import main
        self.assertIs(app.main, main.main)

    def test_app_does_not_create_a_second_application(self):
        import app
        self.assertTrue(callable(app.main))


if __name__ == "__main__":
    unittest.main(verbosity=2)
