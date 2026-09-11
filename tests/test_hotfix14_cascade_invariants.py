from unittest.mock import patch
from providers import SEATS, ProviderError, call_seat

def test_success_at_candidate_one_stops_cascade():
    seat = next(s for s in SEATS if s.key == 'gemini')
    seen = []
    def fake(*args, **kwargs):
        seen.append(args[2]); return 'ok'
    with patch('providers.call_official', side_effect=fake):
        r = call_seat(seat, 'x', '', 1, False, 'key', [], ('m1','m2','m3'), None, 'RID')
    assert seen == ['m1']
    assert r['executed_model'] == 'm1'
    assert r['attempted_models'] == ['m1']

def test_success_at_candidate_two_stops_before_three():
    seat = next(s for s in SEATS if s.key == 'gemini')
    seen = []
    def fake(*args, **kwargs):
        seen.append(args[2])
        if args[2] == 'm1': raise ProviderError('retry', 429, 'http_429_rate_limit_or_quota')
        return 'ok'
    with patch('providers.call_official', side_effect=fake):
        r = call_seat(seat, 'x', '', 1, False, 'key', [], ('m1','m2','m3'), None, 'RID')
    assert seen == ['m1','m2']
    assert r['executed_model'] == 'm2'
    assert r['attempted_models'] == seen
