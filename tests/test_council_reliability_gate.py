from copy import deepcopy
from unittest.mock import Mock

import main
from conversation_runtime import ensure_conversation_state
from conversation_store import hydrate_canonical_record, load_canonical_snapshot


class SessionState(dict):
    pass


def _success(seat, request_id, round_no, model_names):
    executed = model_names[-1]
    return {
        "seat": seat.key,
        "name": seat.name,
        "label": seat.label,
        "status": "SUCCESS",
        "classification": "SUCCESS",
        "mode": "official",
        "model": executed,
        "executed_model": executed,
        "provider_reported_model": executed,
        "content": f"saved response from {seat.name}",
        "attempted_models": list(model_names),
        "cascade_position": len(model_names),
        "attempt_diagnostics": [],
        "runtime_execution_events": [
            {
                "execution_started": True,
                "provider": seat.name,
                "attempt": index,
                "model": model,
                "request_id": request_id,
                "round": round_no,
                "classification": "SUCCESS" if index == len(model_names) else "RATE_LIMITED",
                "cascade_action": "SUCCESS" if index == len(model_names) else "CASCADE_CONTINUE",
                "status": "SUCCESS" if index == len(model_names) else "FAILED",
                "execution_time": 0.01,
                "attempt_id": f"{request_id}:r{round_no}:a{index}",
            }
            for index, model in enumerate(model_names, start=1)
        ],
        "request_id": request_id,
        "round": round_no,
        "request_routed": True,
        "model_candidates_configured": True,
    }


def _provider_failure(seat, request_id, round_no):
    models = [f"{seat.key}-free-1", f"{seat.key}-free-2"]
    events = [
        {
            "execution_started": True,
            "provider": seat.name,
            "attempt": index,
            "model": model,
            "request_id": request_id,
            "round": round_no,
            "classification": "MODEL_UNAVAILABLE",
            "cascade_action": "CASCADE_CONTINUE",
            "status": "FAILED",
            "status_code": 404,
            "execution_time": 0.01,
            "attempt_id": f"{request_id}:r{round_no}:a{index}",
        }
        for index, model in enumerate(models, start=1)
    ]
    return {
        "seat": seat.key,
        "name": seat.name,
        "label": seat.label,
        "status": "FAILED",
        "classification": "MODEL_UNAVAILABLE",
        "mode": "official",
        "model": models[-1],
        "executed_model": models[-1],
        "provider_reported_model": "",
        "content": "",
        "attempted_models": models,
        "attempt_diagnostics": [],
        "runtime_execution_events": events,
        "request_id": request_id,
        "round": round_no,
        "request_routed": True,
        "model_candidates_configured": True,
    }


def _not_configured(seat, request_id, round_no):
    return {
        "seat": seat.key,
        "name": seat.name,
        "label": seat.label,
        "status": "NOT_CONFIGURED",
        "classification": "NOT_CONFIGURED",
        "mode": "official",
        "model": "",
        "executed_model": "",
        "provider_reported_model": "",
        "content": "",
        "attempted_models": [],
        "attempt_diagnostics": [],
        "runtime_execution_events": [],
        "request_id": request_id,
        "round": round_no,
        "request_routed": False,
        "model_candidates_configured": False,
        "dispatch_reason": "FREE_MODEL_LIST_EMPTY",
    }


def test_reliability_gate_keeps_successes_when_another_provider_fails_and_roundtrips():
    ss = SessionState()
    main.st.session_state = ss
    chat = {
        "id": "reliability-gate-conversation",
        "messages": [],
        "request_records": [],
        "history_identity_ledger": [],
        "result_keys": [],
        "audit_events": [],
    }
    ensure_conversation_state(chat)

    request_id = "reliability-gate-request-1"
    round_calls = []

    def fake_run_round(
        user_prompt, current_chat, round_no, credentials, attachments,
        model_candidates, current_user_message_id, deadline, rid, bridge_controls,
    ):
        round_calls.append((rid, round_no))
        results = []
        for seat in main.get_seats():
            if seat.key == "gemini":
                result = _success(seat, rid, round_no, ["gemini-free-1", "gemini-free-2", "gemini-free-3"])
            elif seat.key == "deepseek":
                result = _success(seat, rid, round_no, ["deepseek-free-1"])
            elif seat.key == "claude":
                result = _provider_failure(seat, rid, round_no)
            else:
                result = _not_configured(seat, rid, round_no)
            results.append(result)
        return results

    monkeypatch_identity = Mock(return_value=True)
    original_session_state = main.st.session_state
    main.st.session_state = ss
    try:
        # A completed Request ID must be served from its result cache, not re-run.
        from unittest.mock import patch
        with patch("main._run_round", side_effect=fake_run_round) as provider_round, patch(
            "main._provider_identity_matches", side_effect=monkeypatch_identity
        ):
            first = main._run_council(
                "reliability gate test", chat, 1,
                {"gemini": "test-credential", "deepseek": "test-credential", "claude": "test-credential"},
                [],
                {
                    "gemini": ("gemini-free-1", "gemini-free-2", "gemini-free-3"),
                    "deepseek": ("deepseek-free-1",),
                    "claude": ("claude-free-1", "claude-free-2"),
                },
                "reliability-gate-message-1",
                request_id,
            )
            message_count_after_first = len(chat["messages"])
            second = main._run_council(
                "reliability gate test", chat, 1,
                {"gemini": "test-credential", "deepseek": "test-credential", "claude": "test-credential"},
                [],
                {
                    "gemini": ("gemini-free-1", "gemini-free-2", "gemini-free-3"),
                    "deepseek": ("deepseek-free-1",),
                    "claude": ("claude-free-1", "claude-free-2"),
                },
                "reliability-gate-message-1",
                request_id,
            )
            assert provider_round.call_count == 1
    finally:
        main.st.session_state = original_session_state

    assert round_calls == [(request_id, 1)]
    assert len(first) == len({row["seat"] for row in first})
    assert [row["result_key"] for row in first] == [row["result_key"] for row in second]
    assert len(chat["messages"]) == message_count_after_first

    # The failed Claude execution must not erase either successful provider response.
    visible = {row["seat_key"]: row for row in chat["messages"] if row.get("role") == "assistant"}
    assert set(visible) == {"gemini", "deepseek"}
    assert visible["gemini"]["model"] == visible["gemini"]["executed_model"] == "gemini-free-3"
    assert visible["deepseek"]["model"] == visible["deepseek"]["executed_model"] == "deepseek-free-1"
    assert visible["gemini"]["provider_reported_model"] == visible["gemini"]["executed_model"]
    assert visible["deepseek"]["provider_reported_model"] == visible["deepseek"]["executed_model"]

    live_request = next(row for row in chat["request_records"] if row.get("request_id") == request_id)
    statuses = {row["seat"]: row["status"] for row in live_request["results"]}
    assert statuses["gemini"] == "SUCCESS"
    assert statuses["deepseek"] == "SUCCESS"
    assert statuses["claude"] == "FAILED"
    assert statuses["openai"] == "NOT_CONFIGURED"
    assert len({(row["request_id"], row["round"], row["seat"]) for row in live_request["results"]}) == len(live_request["results"])

    # Reload from the one canonical snapshot: request results and successful response
    # content remain available for the read-only UI fallback after a transient message
    # projection is narrowed or rebuilt.
    snapshot = load_canonical_snapshot(chat, ss)
    assert snapshot is not None
    saved_request = next(row for row in snapshot["requests"] if row.get("request_id") == request_id)
    saved_results = {row["seat"]: row for row in saved_request["results"]}
    assert saved_results["gemini"]["content"] == "saved response from Gemini"
    assert saved_results["deepseek"]["content"] == "saved response from DeepSeek"
    assert saved_results["claude"]["status"] == "FAILED"

    reopened = {
        "conversation_id": chat["conversation_id"],
        "session_id": chat["session_id"],
        "conversation_record": {},
        "request_records": [],
        "messages": [],
        "round_ledger": [],
    }
    hydrate_canonical_record(reopened, ss)
    restored = load_canonical_snapshot(reopened, ss)
    assert restored is not None
    reopened_request = next(row for row in restored["requests"] if row.get("request_id") == request_id)
    reopened_results = {row["seat"]: row for row in reopened_request["results"]}
    assert reopened_results["gemini"]["content"] == "saved response from Gemini"
    assert reopened_results["deepseek"]["content"] == "saved response from DeepSeek"
    assert reopened_results["claude"]["status"] == "FAILED"
