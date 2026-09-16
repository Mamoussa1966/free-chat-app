from unittest.mock import patch

import main


def test_hotfix83_bridge_passes_prior_agent_output_to_later_agent(monkeypatch):
    seen = {}

    seats = main.get_seats()
    by_key = {s.key: s for s in seats}

    def fake_call_seat(seat, user_prompt, shared_context, round_no, local_fallback,
                       credential, attachments=None, model_candidates=None,
                       deadline=None, request_id=""):
        seen[seat.key] = shared_context
        model = (model_candidates or ("test-model",))[0]
        content = "BRIDGE_WRITE: HOTFIX90" if seat.key == "deepseek" else f"RESPONSE:{seat.key}"
        return {
            "seat": seat.key, "name": seat.name, "label": seat.label,
            "status": "SUCCESS", "mode": "official", "model": model,
            "executed_model": model, "provider_reported_model": model,
            "content": content, "error": None, "latency": 0.001,
            "attempted_models": [model], "attempt_diagnostics": [],
            "attempt_summaries": [], "official_authenticated": True,
            "request_id": request_id, "round": round_no,
        }

    monkeypatch.setattr(main, "call_seat", fake_call_seat)
    credentials = {s.key: "TEST" for s in seats}
    candidates = {s.key: ("test-model",) for s in seats}
    chat = {"messages": [], "request_ids": [], "request_records": [],
            "history_identity_ledger": [], "result_keys": []}

    results = main._run_round("bridge", chat, 1, credentials, [], candidates, "u1", None, "r1")

    assert "BRIDGE_WRITE: HOTFIX90" in seen["gemini"]
    assert "Room seat: 7" in seen["gemini"]
    assert "Provider identity: DeepSeek" in seen["gemini"]
    assert [r["seat"] for r in results] == [s.key for s in seats]


def test_hotfix83_bridge_does_not_override_authoritative_identity(monkeypatch):
    seen = {}
    seats = main.get_seats()

    def fake_call_seat(seat, user_prompt, shared_context, round_no, local_fallback,
                       credential, attachments=None, model_candidates=None,
                       deadline=None, request_id=""):
        seen[seat.key] = shared_context
        model = (model_candidates or ("test-model",))[0]
        return {
            "seat": seat.key, "name": seat.name, "label": seat.label,
            "status": "SUCCESS", "mode": "official", "model": model,
            "executed_model": model, "provider_reported_model": model,
            "content": "OK", "error": None, "latency": 0.001,
            "attempted_models": [model], "attempt_diagnostics": [],
            "attempt_summaries": [], "official_authenticated": True,
            "request_id": request_id, "round": round_no,
        }

    monkeypatch.setattr(main, "call_seat", fake_call_seat)
    credentials = {s.key: "TEST" for s in seats}
    candidates = {s.key: ("test-model",) for s in seats}
    chat = {"messages": [], "request_ids": [], "request_records": [],
            "history_identity_ledger": [], "result_keys": []}

    main._run_round("identity", chat, 1, credentials, [], candidates, "u2", None, "r2")
    assert "Room seat: 999" not in seen["gemini"]
