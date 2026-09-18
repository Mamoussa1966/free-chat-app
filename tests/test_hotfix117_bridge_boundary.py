from pathlib import Path

import main
from providers import _prompt


def _result(seat, content, model="test-model", request_id="rid117", round_no=1):
    return {
        "status": "SUCCESS",
        "seat": seat.key,
        "model": model,
        "executed_model": model,
        "content": content,
        "round": round_no,
        "request_id": request_id,
    }


def test_hotfix117_gemini_prompt_contains_neither_bridge_key_nor_value():
    ds = next(s for s in main.get_seats() if s.key == "deepseek")
    gem = next(s for s in main.get_seats() if s.key == "gemini")
    bridge = main.SharedContextBridge(request_id="rid117-a", round_no=1)
    value = "HOTFIX118-CANARY-9Q7X"
    bridge.append_agent_output(ds, _result(ds, f"BRIDGE_WRITE: BRIDGE_RESULT = {value}"))
    bridge.commit(gem)
    bridge.barrier()
    user = bridge.sanitize_user_prompt("bridge isolation test")
    prompt = _prompt(user, bridge.prompt_snapshot(gem), 1, gem, "gemini-3.8-flash")
    assert "BRIDGE_RESULT" not in prompt
    assert value not in prompt
    bridge.record_provider_input(gem, prompt)
    audit = bridge.transaction_audit(user_prompt="bridge isolation test")
    assert audit["GEMINI_INPUT_PROMPT_CONTAINS_VALUE"] == "NO"
    assert audit["BRIDGE_STATE_CONTAINS_VALUE"] == "YES"


def test_hotfix117_read_is_application_owned_and_happens_after_barrier():
    ds = next(s for s in main.get_seats() if s.key == "deepseek")
    gem = next(s for s in main.get_seats() if s.key == "gemini")
    bridge = main.SharedContextBridge(request_id="rid117-b", round_no=1)
    value = "HOTFIX118-READ-AFTER-BARRIER"
    bridge.append_agent_output(ds, _result(ds, f"BRIDGE_WRITE: BRIDGE_RESULT = {value}"))
    assert bridge.read("BRIDGE_RESULT", gem) is None
    bridge.commit(gem)
    assert bridge.read("BRIDGE_RESULT", gem) is None
    bridge.barrier()
    resolved = bridge.consume_read_requests(gem, _result(gem, "normal Gemini response"))
    assert resolved["status"] == "RESOLVED"
    assert resolved["value"] == value
    audit = bridge.transaction_audit(user_prompt="HOTFIX118 bridge isolation test")
    assert audit["WRITE"] == "PASS"
    assert audit["VALIDATE"] == "PASS"
    assert audit["COMMIT"] == "PASS"
    assert audit["BARRIER"] == "PASS"
    assert audit["READ"] == "PASS"
    assert audit["MATCH"] == "PASS"


def test_hotfix117_release_identity_is_canonical():
    assert Path("VERSION.txt").read_text(encoding="utf-8").strip() == "V22.1-HOTFIX118-PRODUCTION-HARDENED"
