from unittest.mock import patch
from providers import SEATS, ProviderError, call_seat

def test_failure_one_then_two_then_three():
    seat=next(x for x in SEATS if x.key=='gemini'); seen=[]
    def fake(*a,**k):
        seen.append(a[2])
        if len(seen)<3: raise ProviderError('transient',500,'provider_server')
        return 'ok'
    with patch('providers.call_official',side_effect=fake): r=call_seat(seat,'x','',1,False,'k',[],('m1','m2','m3'),None)
    assert seen==['m1','m2','m3']; assert r['attempted_models']==seen
