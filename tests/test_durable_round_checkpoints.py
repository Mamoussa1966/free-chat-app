"""Durable Message/Request/Round checkpoint regression tests.

All provider results are synthetic. Storage is replaced with an in-memory
acknowledgement recorder; no Supabase or provider endpoint is contacted.
"""
from __future__ import annotations

import copy

import pytest

from conversation_runtime import ensure_conversation_state


class SS(dict):
    pass


def _fake_result(seat, model: str, request_id: str, round_no: int) -> dict:
    return {
        "status": "SUCCESS",
        "seat": seat.key,
        "name": seat.name,
        "label": seat.label,
        "mode": "official",
        "model": model,
        "executed_model": model,
        "provider_reported_model": model,
        "content": "synthetic result",
        "attempted_models": [model],
        "cascade_position": 1,
        "attempt_diagnostics": [],
        "runtime_execution_events": [
            {
                "execution_started": True,
                "request_id": request_id,
                "round": round_no,
                "attempt": 1,
                "model": model,
                "status": "SUCCESS",
            }
        ],
        "request_id": request_id,
        "round": round_no,
    }


def _install_durable_storage_stub(monkeypatch, *, save_result: bool):
    import main

    session_state = SS()
    monkeypatch.setattr(main.st, "session_state", session_state, raising=False)
    monkeypatch.setattr(
        main,
        "get_supabase_config",
        lambda _st: ("https://example.supabase.co", "sb_publishable_test", True),
    )
    snapshots: list[dict] = []

    def save_checkpoint(chat):
        snapshots.append(copy.deepcopy(chat["conversation_record"]))
        return save_result

    monkeypatch.setattr(main, "_supabase_persist_completed_chat", save_checkpoint)
    monkeypatch.setattr(main, "_provider_identity_matches", lambda *args, **kwargs: True)
    return main, session_state, snapshots


def _chat():
    chat = {
        "id": "durable-round-checkpoint-chat",
        "messages": [],
        "request_records": [],
        "history_identity_ledger": [],
        "result_keys": [],
        "audit_events": [],
    }
    ensure_conversation_state(chat)
    return chat


def test_round_started_is_durably_acknowledged_before_provider_dispatch(monkeypatch):
    main, _, snapshots = _install_durable_storage_stub(monkeypatch, save_result=True)
    chat = _chat()
    seat = next(item for item in main.get_seats() if item.key == "gemini")
    provider_call_snapshots = []

    def fake_round(*args, **kwargs):
        provider_call_snapshots.append(True)
        # The durable checkpoint must already contain the exact lifecycle chain.
        assert len(snapshots) == 1
        started = snapshots[0]
        assert started["messages"][0]["message_id"] == "message-1"
        assert started["requests"][0]["request_id"] == "request-1"
        assert started["requests"][0]["state"] == "RUNNING"
        assert started["rounds"][0]["request_id"] == "request-1"
        assert started["rounds"][0]["status"] == "STARTED"
        assert started["rounds"][0]["round"] == 1
        return [_fake_result(seat, "synthetic-free-model", "request-1", args[2])]

    monkeypatch.setattr(main, "_run_round", fake_round)

    results = main._run_council(
        "durable checkpoint test",
        chat,
        1,
        {seat.key: "synthetic-credential"},
        [],
        {seat.key: ("synthetic-free-model",)},
        "message-1",
        "request-1",
    )

    assert len(provider_call_snapshots) == 1
    assert len(results) == 1
    assert len(snapshots) == 2
    completed_round = snapshots[1]
    assert completed_round["requests"][0]["state"] == "RUNNING"
    assert completed_round["requests"][0]["rounds_executed"] == 1
    assert len(completed_round["requests"][0]["results"]) == 1
    assert completed_round["rounds"][0]["status"] == "COMPLETED"
    assert completed_round["rounds"][0]["result_count"] == 1
    assert completed_round["rounds"][0]["finished_at"]
    assert chat["conversation_record"]["requests"][0]["state"] == "COMPLETED"


def test_failed_round_start_checkpoint_blocks_provider_execution(monkeypatch):
    main, _, snapshots = _install_durable_storage_stub(monkeypatch, save_result=False)
    chat = _chat()
    seat = next(item for item in main.get_seats() if item.key == "gemini")
    provider_calls = []

    def forbidden_provider_call(*args, **kwargs):
        provider_calls.append(True)
        return [_fake_result(seat, "synthetic-free-model", "request-1", args[2])]

    monkeypatch.setattr(main, "_run_round", forbidden_provider_call)

    with pytest.raises(RuntimeError, match="SUPABASE_ROUND_START_CHECKPOINT_NOT_CONFIRMED"):
        main._run_council(
            "storage failure must block provider dispatch",
            chat,
            1,
            {seat.key: "synthetic-credential"},
            [],
            {seat.key: ("synthetic-free-model",)},
            "message-1",
            "request-1",
        )

    assert provider_calls == []
    assert len(snapshots) == 2  # initial RUNNING checkpoint + best-effort FAILED checkpoint
    assert snapshots[0]["rounds"][0]["status"] == "STARTED"
    assert snapshots[1]["requests"][0]["state"] == "FAILED"
    assert snapshots[1]["rounds"][0]["status"] == "STARTED"
    assert chat["conversation_record"]["requests"][0]["state"] == "FAILED"


def test_round_completion_checkpoint_failure_stops_before_a_following_round(monkeypatch):
    main, _, snapshots = _install_durable_storage_stub(monkeypatch, save_result=True)
    chat = _chat()
    seat = next(item for item in main.get_seats() if item.key == "gemini")
    calls = []

    def save_first_only(chat_state):
        snapshots.append(copy.deepcopy(chat_state["conversation_record"]))
        # The pre-dispatch checkpoint succeeds; the post-round checkpoint fails.
        return len(snapshots) == 1

    monkeypatch.setattr(main, "_supabase_persist_completed_chat", save_first_only)

    def fake_round(*args, **kwargs):
        calls.append(args[2])
        return [_fake_result(seat, "synthetic-free-model", "request-1", args[2])]

    monkeypatch.setattr(main, "_run_round", fake_round)

    with pytest.raises(RuntimeError, match="SUPABASE_ROUND_COMPLETION_CHECKPOINT_NOT_CONFIRMED"):
        main._run_council(
            "round completion checkpoint failure",
            chat,
            2,
            {seat.key: "synthetic-credential"},
            [],
            {seat.key: ("synthetic-free-model",)},
            "message-1",
            "request-1",
        )

    assert calls == [1]  # Round 2 is never started without Round 1's durable completion.
    assert len(snapshots) == 3  # start, failed completion save, best-effort FAILED request save
    assert snapshots[0]["rounds"][0]["status"] == "STARTED"
    assert snapshots[1]["rounds"][0]["status"] == "COMPLETED"
    assert snapshots[2]["requests"][0]["state"] == "FAILED"
