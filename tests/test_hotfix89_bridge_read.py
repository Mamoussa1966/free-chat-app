from unittest.mock import patch
import main
import providers


def _result(seat, content, request_id="rid89", round_no=1):
    return {
        "seat": seat.key, "name": seat.name, "label": seat.label,
        "status": "SUCCESS", "mode": "official", "model": "test-model",
        "executed_model": "test-model", "provider_reported_model": "test-model",
        "content": content, "error": None, "latency": 0.001,
        "attempted_models": ["test-model"], "attempt_diagnostics": [],
        "attempt_summaries": [], "official_authenticated": True,
        "request_id": request_id, "round": round_no,
    }


def test_hotfix89_version_contract():
    assert providers.VERSION == "V22.1-HOTFIX91-PRODUCTION-HARDENED"
    assert main.APP_VERSION == "V22.1-HOTFIX91-PRODUCTION-HARDENED"


def test_hotfix89_read_is_available_only_after_commit_and_barrier():
    seats = main.get_seats()
    ds = next(s for s in seats if s.key == "deepseek")
    gem = next(s for s in seats if s.key == "gemini")
    bridge = main.SharedContextBridge(request_id="rid89-ready", round_no=1)
    generated = "HOTFIX91-BRIDGE-READ-7X9Q"
    bridge.append_agent_output(ds, _result(ds, f"BRIDGE_WRITE: BRIDGE_RESULT = {generated}"))
    assert bridge.read("BRIDGE_RESULT", gem) is None
    bridge.commit(gem)
    assert bridge.read("BRIDGE_RESULT", gem) is None
    bridge.barrier()
    assert bridge.read("BRIDGE_RESULT", gem) == generated


def test_hotfix89_resolves_gemini_read_without_putting_value_in_gemini_prompt(monkeypatch):
    seen = {}
    seats = main.get_seats()

    def fake_call(seat, user_prompt, shared_context, round_no, local_fallback,
                  credential, attachments=None, model_candidates=None,
                  deadline=None, request_id=""):
        seen[seat.key] = shared_context
        model = (model_candidates or ("m",))[0]
        if seat.key == "deepseek":
            content = "BRIDGE_WRITE: BRIDGE_RESULT = DS89-ONLY-IN-BRIDGE-STATE"
        elif seat.key == "gemini":
            content = "BRIDGE_READ: BRIDGE_RESULT"
        else:
            content = "NO_TEST_ACTION"
        return _result(seat, content, request_id=request_id, round_no=round_no) | {
            "model": model, "executed_model": model, "provider_reported_model": model,
            "attempted_models": [model]
        }

    monkeypatch.setattr(main, "call_seat", fake_call)
    credentials = {s.key: "TEST" for s in seats}
    models = {s.key: ("m",) for s in seats}
    chat = {"messages": [], "request_ids": [], "request_records": [],
            "history_identity_ledger": [], "result_keys": []}
    out = main._run_round("bridge", chat, 1, credentials, [], models, "u", None, "rid89")
    gemini = next(r for r in out if r["seat"] == "gemini")
    assert "DS89-ONLY-IN-BRIDGE-STATE" not in seen["gemini"]
    assert "BRIDGE READ AVAILABLE (VALUE NOT IN PROMPT)" in seen["gemini"]
    assert gemini["bridge_read_status"] == "PASS"
    assert gemini["bridge_schema_validation"] == "PASS"
    assert gemini["content"] == "DS89-ONLY-IN-BRIDGE-STATE"
    assert gemini["bridge_trace"][-1]["target_seat"] == 2
    assert gemini["bridge_trace"][-1]["read_sequence"] == 1
    assert gemini["bridge_trace"][-1]["commit_status"] == "COMMITTED"
    assert gemini["bridge_trace"][-1]["schema_validation"] == "PASS"


def test_hotfix89_not_ready_is_closed_without_guessing():
    seats = main.get_seats()
    gem = next(s for s in seats if s.key == "gemini")
    bridge = main.SharedContextBridge(request_id="rid89-not-ready", round_no=1)
    result = _result(gem, "BRIDGE_READ: BRIDGE_RESULT")
    resolution = bridge.consume_read_requests(gem, result)
    assert resolution["status"] == "NOT_READY"
    assert resolution["reads"][0]["value"] is None
