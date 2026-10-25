import time
from unittest.mock import patch
import providers
from providers import SEATS, ProviderError, call_seat

def test_failure_one_then_two_then_three():
    seat=next(x for x in SEATS if x.key=='gemini'); seen=[]
    def fake(*a,**k):
        seen.append(a[2])
        if len(seen)<3: raise ProviderError('transient',500,'provider_server')
        return 'ok'
    with patch('providers.call_official',side_effect=fake): r=call_seat(seat,'x','',1,False,'k',[],('m1','m2','m3'),None)
    assert seen==['m1','m2','m3']; assert r['attempted_models']==seen


def test_opt_in_provider_timeout_applies_and_timeout_advances_cascade(monkeypatch):
    seat = next(x for x in SEATS if x.key == 'gemini')
    seen = []

    def fake_call_official(*args, **kwargs):
        model, timeout = args[2], args[4]
        seen.append((model, timeout))
        if model == 'm1':
            raise ProviderError('simulated timeout', error_class='timeout')
        return {'text': 'OK', 'provider_reported_model': model}

    monkeypatch.setattr(providers, '_setting', lambda names: '12' if tuple(names) == ('COUNCIL_PROVIDER_TIMEOUT_SECONDS',) else None)
    monkeypatch.setattr(providers, 'call_official', fake_call_official)
    result = call_seat(seat, 'x', '', 1, False, 'k', [], ('m1', 'm2'), None)

    assert seen == [('m1', 12.0), ('m2', 12.0)]
    assert result['status'] == 'SUCCESS'
    assert result['attempted_models'] == ['m1', 'm2']
    assert result['executed_model'] == 'm2'


def test_global_deadline_caps_configured_provider_timeout(monkeypatch):
    seat = next(x for x in SEATS if x.key == 'gemini')
    seen = {}

    def fake_call_official(*args, **kwargs):
        seen['timeout'] = args[4]
        return {'text': 'OK', 'provider_reported_model': args[2]}

    monkeypatch.setattr(providers, '_setting', lambda names: '12' if tuple(names) == ('COUNCIL_PROVIDER_TIMEOUT_SECONDS',) else None)
    monkeypatch.setattr(providers, 'call_official', fake_call_official)
    result = call_seat(seat, 'x', '', 1, False, 'k', [], ('m1',), time.monotonic() + 2.0)

    assert result['status'] == 'SUCCESS'
    assert 0 < seen['timeout'] <= 2.0
