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

def test_attempt_diagnostics_identify_each_failed_candidate_and_stop_at_success():
    seat = next(s for s in SEATS if s.key == 'gemini')
    def fake(*args, **kwargs):
        model = args[2]
        if model == 'm1':
            raise ProviderError('model missing', 404, 'model_not_found_or_invalid')
        if model == 'm2':
            raise ProviderError('quota', 429, 'http_429_rate_limit_or_quota')
        return 'ok'
    with patch('providers.call_official', side_effect=fake):
        r = call_seat(seat, 'x', '', 1, False, 'key', [], ('m1','m2','m3'), None, 'RID')
    assert r['attempted_models'] == ['m1', 'm2', 'm3']
    assert r['executed_model'] == 'm3'
    assert [(d['attempt'], d['model'], d['error_class'], d['status_code']) for d in r['attempt_diagnostics']] == [
        (1, 'm1', 'model_not_found_or_invalid', 404),
        (2, 'm2', 'http_429_rate_limit_or_quota', 429),
    ]
    assert all(d['will_continue'] is True for d in r['attempt_diagnostics'])


def test_attempt_diagnostics_are_empty_when_first_candidate_succeeds():
    seat = next(s for s in SEATS if s.key == 'gemini')
    with patch('providers.call_official', return_value='ok'):
        r = call_seat(seat, 'x', '', 1, False, 'key', [], ('m1','m2'), None, 'RID')
    assert r['attempted_models'] == ['m1']
    assert r['executed_model'] == 'm1'
    assert r['attempt_diagnostics'] == []

def test_attempt_diagnostics_are_durable_for_every_failed_attempt_before_success():
    seat = next(s for s in SEATS if s.key == 'gemini')
    def fake(*args, **kwargs):
        model = args[2]
        if model == 'm1':
            raise ProviderError('model unavailable', 404, 'model_not_found_or_invalid')
        if model == 'm2':
            raise ProviderError('rate limited', 429, 'http_429_rate_limit_or_quota')
        return 'ok'
    with patch('providers.call_official', side_effect=fake):
        r = call_seat(seat, 'x', '', 1, False, 'key', [], ('m1','m2','m3'), None, 'RID')
    assert r['attempted_models'] == ['m1', 'm2', 'm3']
    assert len(r['attempt_diagnostics']) == 2
    assert [d['model'] for d in r['attempt_diagnostics']] == ['m1', 'm2']
    assert [d['error_class'] for d in r['attempt_diagnostics']] == ['model_not_found_or_invalid', 'http_429_rate_limit_or_quota']
    assert [d['status_code'] for d in r['attempt_diagnostics']] == [404, 429]
    assert [d['will_continue'] for d in r['attempt_diagnostics']] == [True, True]
