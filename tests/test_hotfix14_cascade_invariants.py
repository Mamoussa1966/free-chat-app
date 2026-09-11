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


def test_hotfix14_required_path_first_fails_second_succeeds_and_stops():
    """Regression: #1 retryable failure -> #2 success; #3 must never execute."""
    seat = next(s for s in SEATS if s.key == "gemini")
    executed = []

    def fake_call_official(seat, prompt, model, credential, timeout, attachments=None, deadline=None):
        executed.append(model)
        if model == "m1":
            raise ProviderError("forced retryable failure", error_class="transient")
        return "OK-SECOND"

    with patch("providers.call_official", side_effect=fake_call_official):
        result = call_seat(
            seat, "x", "", 1, False, "key", [], ("m1", "m2", "m3"), None, "REQ-HF14"
        )

    assert executed == ["m1", "m2"]
    assert result["attempted_models"] == ["m1", "m2"]
    assert result["executed_model"] == "m2"
    assert result["model"] == "m2"
    assert result["request_id"] == "REQ-HF14"
    assert result["round"] == 1
    assert "m3" not in executed
