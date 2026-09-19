from pathlib import Path
import main
from production_core import RequestRoundExecutionRegistry


def test_hotfix120_2_one_round_one_seat_one_request():
    ledger = main.SeatExecutionLedger("req-120-2", 1)
    first = ledger.claim("deepseek")
    assert first == ledger.snapshot()["deepseek"]
    try:
        ledger.claim("deepseek")
        assert False, "same request + round + seat must not execute twice"
    except RuntimeError:
        pass


def test_hotfix120_2_one_round_one_bridge_scope():
    rounds = RequestRoundExecutionRegistry("req-bridge-120-2")
    assert rounds.claim_round(1) == "req-bridge-120-2:r1"
    try:
        rounds.claim_round(1)
        assert False, "same request + round must not create a second bridge scope"
    except RuntimeError:
        pass


def test_hotfix120_2_ten_cascade_attempts_share_one_request_id():
    request_id = "req-cascade-120-2"
    details = [
        {"request_id": request_id, "round": 1, "attempt": n,
         "model": f"m{n}", "classification": "MODEL_UNAVAILABLE",
         "cascade_action": "CASCADE_CONTINUE" if n < 10 else "CASCADE_STOP"}
        for n in range(1, 11)
    ]
    assert len(details) == 10
    assert {d["request_id"] for d in details} == {request_id}
    assert {d["round"] for d in details} == {1}
    assert [d["attempt"] for d in details] == list(range(1, 11))


def test_hotfix120_2_secondary_orchestrator_path_is_blocked():
    chat = main._new_chat()
    chat["request_records"].append({"request_id": "req-secondary", "state": "RUNNING"})
    main._ACTIVE_ORCHESTRATOR_REQUESTS.add("req-secondary")
    try:
        try:
            main._run_council("x", chat, 1, {}, [], {}, "msg", "req-secondary")
            assert False, "secondary orchestrator execution must be blocked"
        except RuntimeError as exc:
            assert "Duplicate orchestrator execution blocked" in str(exc)
    finally:
        main._ACTIVE_ORCHESTRATOR_REQUESTS.discard("req-secondary")


def test_hotfix120_2_release_identity():
    assert Path("VERSION.txt").read_text(encoding="utf-8").strip() == "V22.1-HOTFIX121.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE"
