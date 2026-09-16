import main


def test_hotfix85_seat7_write_reaches_gemini_seat2(monkeypatch):
    seen = {}
    seats = main.get_seats()

    def fake_call_seat(seat, user_prompt, shared_context, round_no, local_fallback,
                       credential, attachments=None, model_candidates=None,
                       deadline=None, request_id=""):
        seen[seat.key] = shared_context
        model = (model_candidates or ("test-model",))[0]
        if seat.key == "deepseek":
            content = "BRIDGE_WRITE: BRIDGE_RESULT = DEEPSEEK-7-WROTE-7319"
        elif seat.key == "gemini":
            assert "Key: BRIDGE_RESULT" in shared_context
            assert "DEEPSEEK-7-WROTE-7319" not in shared_context
            content = "DEEPSEEK-7-WROTE-7319"
        else:
            content = "OK"
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

    results = main._run_round(
        "Write a provider bridge value and then allow later providers to read it.",
        chat, 1, credentials, [], candidates, "u85", None, "r85"
    )

    assert "BRIDGE READ AVAILABLE (VALUE NOT IN PROMPT)" in seen["gemini"]
    assert "Key: BRIDGE_RESULT" in seen["gemini"]
    assert "DEEPSEEK-7-WROTE-7319" not in seen["gemini"]
    assert [r["seat"] for r in results] == [s.key for s in seats]
