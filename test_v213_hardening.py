import unittest
from providers import _parse_models, _retry_delay

class V213CompatibilityTests(unittest.TestCase):
    def test_model_override_is_bounded_and_deduplicated(self):
        self.assertEqual(_parse_models("a,b,a,c,d,e"), ("a", "b", "c", "d", "e"))
    def test_retry_after_is_bounded(self):
        response = type("Response", (), {"headers": {"Retry-After": "999"}})()
        self.assertEqual(_retry_delay(response, 0), 5.0)

if __name__ == "__main__": unittest.main()
