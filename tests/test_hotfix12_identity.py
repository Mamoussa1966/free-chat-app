import unittest
from unittest.mock import patch
import providers

class Hotfix12IdentityTests(unittest.TestCase):
    def test_result_identity_matches_first_api_argument(self):
        with patch('providers.call_official', return_value='OK') as call:
            result = providers.call_seat(providers.SEATS[1], 'hello', '', 1, False, 'key', [], ('m1','m2','m3'), None)
        self.assertEqual(call.call_args.args[2], 'm1')
        self.assertEqual(result['model'], 'm1')
        self.assertEqual(result['attempted_models'], ['m1'])

if __name__ == '__main__': unittest.main()
