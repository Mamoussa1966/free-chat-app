from pathlib import Path
import main

def _result(seat, content, model="test-model", request_id="rid119", round_no=1):
    return {"status":"SUCCESS","seat":seat.key,"model":model,"executed_model":model,"content":content,"round":round_no,"request_id":request_id}

def test_hotfix119_application_owned_read_is_resolved_before_target_http():
    ds = next(s for s in main.get_seats() if s.key == "deepseek")
    gem = next(s for s in main.get_seats() if s.key == "gemini")
    bridge = main.SharedContextBridge(request_id="rid119-read", round_no=1)
    value = "HOTFIX123-READ-CANARY-7Q9X"
    bridge.append_agent_output(ds, _result(ds, f"BRIDGE_WRITE: BRIDGE_RESULT = {value}"))
    bridge.commit(gem)
    bridge.barrier()
    resolved = bridge.read("BRIDGE_RESULT", gem)
    assert resolved == value
    prompt = bridge.sanitize_user_prompt("transactional bridge isolation test")
    assert value not in prompt
    assert "BRIDGE_RESULT" not in prompt
    bridge.record_provider_input(gem, prompt)
    bridge.record_runtime_payload_attestation(gem, {"payload_sha256":"canary","payload_json":prompt})
    audit = bridge.seal_runtime_audit(user_prompt="transactional bridge isolation test")
    assert audit["READ"] == "PASS"
    assert audit["SCHEMA_VALIDATION"] == "PASS"
    assert audit["MATCH"] == "PASS"
    assert audit["GEMINI_INPUT_PROMPT_CONTAINS_VALUE"] == "NO"
    assert audit["BRIDGE_STATE_CONTAINS_VALUE"] == "YES"

def test_hotfix119_release_identity():
    assert Path("VERSION.txt").read_text(encoding="utf-8").strip() == "V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE"
