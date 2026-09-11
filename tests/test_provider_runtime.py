from unittest.mock import patch
from providers import SEATS, call_seat

def test_router_starts_at_candidate_one():
    seat=next(x for x in SEATS if x.key=='gemini'); seen=[]
    def fake(*a,**k): seen.append(a[2]); return 'OK'
    with patch('providers.call_official',side_effect=fake):
        r=call_seat(seat,'x','',1,False,'key',[],('m1','m2','m3'),None)
    assert seen==['m1']; assert r['executed_model']=='m1'; assert r['model']=='m1'

def test_router_never_skips_candidate_two():
    seat=next(x for x in SEATS if x.key=='gemini'); seen=[]
    def fake(*a,**k):
        seen.append(a[2])
        if a[2] != 'm3':
            from providers import ProviderError
            raise ProviderError('retry',429,'http_429_rate_limit_or_quota')
        return 'OK'
    with patch('providers.call_official',side_effect=fake):
        r=call_seat(seat,'x','',1,False,'key',[],('m1','m2','m3'),None)
    assert seen==['m1','m2','m3']; assert r['executed_model']=='m3'; assert r['attempted_models']==seen
