from conversation_runtime import ensure_conversation_state
from conversation_store import prepare_historical_runtime
from conversation_v25_runtime import authoritative_audit


class SS(dict):
    pass


def _fake_result(seat, model, request_id, round_no):
    return {
        "status": "SUCCESS",
        "seat": seat.key,
        "name": seat.name,
        "label": seat.label,
        "mode": "official",
        "model": model,
        "executed_model": model,
        "provider_reported_model": model,
        "content": "ok",
        "attempted_models": [model],
        "cascade_position": 1,
        "attempt_diagnostics": [],
        "runtime_execution_events": [{"execution_started": True, "request_id": request_id, "round": round_no}],
        "request_id": request_id,
        "round": round_no,
    }


def test_hotfix129_two_real_turns_survive_runtime_narrowing(monkeypatch):
    import main

    ss = SS()
    monkeypatch.setattr(main.st, "session_state", ss, raising=False)
    chat = {"id": "conv-hf129", "messages": [], "request_records": [], "history_identity_ledger": [], "result_keys": [], "audit_events": []}
    ensure_conversation_state(chat)
    seat = next(s for s in main.get_seats() if s.key == "gemini")

    monkeypatch.setattr(
        main,
        "_run_round",
        lambda *args, **kwargs: [_fake_result(seat, "test-model", args[2] if len(args) > 2 else kwargs["request_id"], args[1] if len(args) > 1 else kwargs["round_no"])],
    )
    monkeypatch.setattr(main, "_provider_identity_matches", lambda *a, **k: True)

    main._run_council("MESSAGE_1", chat, 1, {seat.key: "key"}, [], {seat.key: ("test-model",)}, "message-1", "request-1")

    # Simulate the important Streamlit rerun failure mode: the live object is narrowed
    # to the current request. The canonical transport must restore the full history
    # before the second real user submission is executed.
    chat["conversation_record"] = {
        "conversation_id": chat["conversation_id"],
        "session_id": chat["session_id"],
        "messages": [chat["conversation_record"]["messages"][-1]],
        "requests": [chat["conversation_record"]["requests"][-1]],
        "rounds": [chat["conversation_record"]["rounds"][-1]],
    }
    prepare_historical_runtime(chat, ss)
    assert len(chat["conversation_record"]["messages"]) == 1
    assert len(chat["conversation_record"]["requests"]) == 1
    assert len(chat["conversation_record"]["rounds"]) == 1

    main._run_council("MESSAGE_2", chat, 1, {seat.key: "key"}, [], {seat.key: ("test-model",)}, "message-2", "request-2")
    audit = authoritative_audit(chat, ss)

    assert audit["canonical_message_count"] == 2
    assert audit["canonical_request_count"] == 2
    assert audit["canonical_round_count"] == 2
    assert audit["message_1_request_1_exact"] if "message_1_request_1_exact" in audit else audit["canonical_round_identity_evidence"]["message_1_request_1_exact"]
    assert audit["canonical_round_identity_evidence"]["message_2_request_2_exact"] is True
    assert audit["request_1_round_1_mapping"] is True
    assert audit["request_2_round_2_mapping"] is True
    assert audit["request_2_round_1_mapping"] is False
    assert audit["canonical_round_ordinals"] == [1, 2]
    assert audit["canonical_round_sequence_proven"] is True
    assert audit["conversation_runtime_audit"] == "PASS"
    assert audit["overall_authoritative_status"] == "PASS"


def test_hotfix129_one_turn_cannot_fabricate_round_two(monkeypatch):
    import main

    ss = SS()
    monkeypatch.setattr(main.st, "session_state", ss, raising=False)
    chat = {"id": "conv-hf129-single", "messages": [], "request_records": [], "history_identity_ledger": [], "result_keys": [], "audit_events": []}
    ensure_conversation_state(chat)
    seat = next(s for s in main.get_seats() if s.key == "gemini")
    monkeypatch.setattr(main, "_run_round", lambda *args, **kwargs: [_fake_result(seat, "test-model", args[2], args[1])])
    monkeypatch.setattr(main, "_provider_identity_matches", lambda *a, **k: True)

    main._run_council("ONLY_MESSAGE_1", chat, 1, {seat.key: "key"}, [], {seat.key: ("test-model",)}, "message-1", "request-1")
    audit = authoritative_audit(chat, ss)

    assert audit["canonical_message_count"] == 1
    assert audit["canonical_request_count"] == 1
    assert audit["canonical_round_count"] == 1
    assert audit["request_2_round_2_mapping"] == "NOT_PROVEN"
    assert audit["overall_authoritative_status"] == "NOT_PROVEN"
