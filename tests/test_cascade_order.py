import unittest
from unittest.mock import patch
import providers

class CascadeOrderTests(unittest.TestCase):
    def _run(self, failures):
        executed=[]
        def fake(*args, **kwargs):
            model=args[2]; executed.append(model)
            if model in failures: raise providers.ProviderError('retry',429,'transient')
            return 'OK'
        with patch('providers.call_official', side_effect=fake):
            result=providers.call_seat(providers.SEATS[1],'hello','',1,False,'key',[],('m1','m2','m3'),None)
        return result, executed
    def test_never_skip_2_when_1_fails(self):
        result, executed=self._run({'m1','m2'})
        self.assertEqual(executed,['m1','m2','m3'])
        self.assertEqual(result['attempted_models'],executed)
    def test_success_1_stops_cascade(self):
        result, executed=self._run(set())
        self.assertEqual(executed,['m1'])
        self.assertEqual(result['model'],'m1')
    def test_success_2_stops_before_3(self):
        result, executed=self._run({'m1'})
        self.assertEqual(executed,['m1','m2'])
        self.assertEqual(result['model'],'m2')
    def test_no_duplicate_model_execution(self):
        _, executed=self._run({'m1','m2'})
        self.assertEqual(len(executed),len(set(executed)))

if __name__=='__main__': unittest.main()
