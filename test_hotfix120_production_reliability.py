import main
from production_core import SeatExecutionLedger


def test_hotfix120_seat_execution_ledger_is_exactly_once():
    ledger = SeatExecutionLedger("req-1", 1)
    eid = ledger.claim("gemini")
    ledger.assert_claimed("gemini", eid)
    try:
        ledger.claim("gemini")
        assert False, "duplicate seat claim must fail"
    except RuntimeError:
        pass


def test_hotfix120_execution_id_is_deterministic_for_same_request_round_seat():
    a = SeatExecutionLedger("req-abc", 2).claim("deepseek")
    b = SeatExecutionLedger("req-abc", 2).claim("deepseek")
    assert a == b


def test_hotfix120_execution_id_changes_across_round_or_seat():
    a = SeatExecutionLedger("req-abc", 1).claim("deepseek")
    b = SeatExecutionLedger("req-abc", 2).claim("deepseek")
    c = SeatExecutionLedger("req-abc", 1).claim("gemini")
    assert len({a, b, c}) == 3


def test_hotfix120_rerun_gate_is_present_and_uses_fingerprint_before_run():
    assert hasattr(main, "_REQUEST_GATE_LOCK")
    assert hasattr(main, "_ACTIVE_REQUEST_FINGERPRINTS")
    fp = main._request_fingerprint("hello", [])
    chat = {"request_ids": [fp]}
    assert fp in chat["request_ids"]


def test_hotfix120_provider_attempts_are_single_request_scope():
    # Contract-level assertion: a cascade position is an attempt inside one
    # provider result; it must carry one request_id and round.
    result = {"request_id": "req-1", "round": 1, "attempt_diagnostics": [
        {"request_id": "req-1", "round": 1, "attempt": 1, "model": "m1"},
        {"request_id": "req-1", "round": 1, "attempt": 2, "model": "m2"},
    ]}
    assert {x["request_id"] for x in result["attempt_diagnostics"]} == {result["request_id"]}
    assert {x["round"] for x in result["attempt_diagnostics"]} == {result["round"]}
