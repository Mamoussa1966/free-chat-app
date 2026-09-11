import unittest
from unittest.mock import patch
import providers

class ExecutionIdentityTests(unittest.TestCase):
    def test_api_argument_is_authoritative_executed_model(self):
        seen=[]
        def fake(*args, **kwargs): seen.append(args[2]); return 'OK'
        with patch('providers.call_official', side_effect=fake):
            result=providers.call_seat(providers.SEATS[1],'hello','',1,False,'key',[],('gemini-3.8-flash','gemini-3.7-flash'),None)
        self.assertEqual(seen,['gemini-3.8-flash'])
        self.assertEqual(result['executed_model'],seen[-1])
        self.assertEqual(result['model'],seen[-1])
        self.assertEqual(result['attempted_models'],seen)
    def test_third_only_after_first_two_fail(self):
        seen=[]
        def fake(*args, **kwargs):
            model=args[2]; seen.append(model)
            if model != 'm3': raise providers.ProviderError('retry',429,'transient')
            return 'OK'
        with patch('providers.call_official', side_effect=fake):
            result=providers.call_seat(providers.SEATS[1],'hello','',1,False,'key',[],('m1','m2','m3'),None)
        self.assertEqual(seen,['m1','m2','m3'])
        self.assertEqual(result['executed_model'],'m3')

if __name__=='__main__': unittest.main()
