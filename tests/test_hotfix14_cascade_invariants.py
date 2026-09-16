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


def test_failure_diagnostics_classify_each_failed_candidate_and_stop_on_success():
    seat = next(s for s in SEATS if s.key == 'gemini')
    seen = []
    def fake(*args, **kwargs):
        model = args[2]
        seen.append(model)
        if model == 'm1':
            raise ProviderError('model not found', 404, 'model_not_found_or_invalid')
        if model == 'm2':
            raise ProviderError('rate limited', 429, 'http_429_rate_limit_or_quota')
        return 'ok'
    with patch('providers.call_official', side_effect=fake):
        r = call_seat(seat, 'x', '', 1, False, 'key', [], ('m1','m2','m3'), None, 'RID')
    assert seen == ['m1', 'm2', 'm3']
    assert r['status'] == 'SUCCESS'
    assert r['executed_model'] == 'm3'
    assert r['attempted_models'] == seen
    assert [d['model'] for d in r['attempt_diagnostics']] == ['m1', 'm2']
    assert [d['error_class'] for d in r['attempt_diagnostics']] == [
        'model_not_found_or_invalid',
        'http_429_rate_limit_or_quota',
    ]
    assert r['attempt_diagnostics'][0]['status_code'] == 404
    assert r['attempt_diagnostics'][1]['status_code'] == 429


def test_terminal_auth_failure_is_recorded_without_advancing_to_next_model():
    seat = next(s for s in SEATS if s.key == 'gemini')
    seen = []
    def fake(*args, **kwargs):
        seen.append(args[2])
        raise ProviderError('bad key', 401, 'http_401_authentication_failed')
    with patch('providers.call_official', side_effect=fake):
        r = call_seat(seat, 'x', '', 1, False, 'key', [], ('m1','m2'), None, 'RID')
    assert seen == ['m1']
    assert r['status'] == 'FAILED'
    assert r['attempt_diagnostics'][0]['error_class'] == 'http_401_authentication_failed'
    assert r['attempt_diagnostics'][0]['status_code'] == 401
