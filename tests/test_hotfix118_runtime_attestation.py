from pathlib import Path
import main
from providers import _prompt


def _result(seat, content, model="test-model", request_id="rid118", round_no=1):
    return {"status":"SUCCESS","seat":seat.key,"model":model,"executed_model":model,"content":content,"round":round_no,"request_id":request_id}


def test_hotfix118_runtime_payload_attestation_is_final_gate():
    ds = next(s for s in main.get_seats() if s.key == "deepseek")
    gem = next(s for s in main.get_seats() if s.key == "gemini")
    bridge = main.SharedContextBridge(request_id="rid118-a", round_no=1)
    value = "HOTFIX123-RUNTIME-CANARY-7Q9X"
    bridge.append_agent_output(ds, _result(ds, f"BRIDGE_WRITE: BRIDGE_RESULT = {value}"))
    bridge.commit(gem); bridge.barrier()
    user = bridge.sanitize_user_prompt("runtime payload isolation test")
    prompt = _prompt(user, bridge.prompt_snapshot(gem), 1, gem, "gemini-3.8-flash")
    assert "BRIDGE_RESULT" not in prompt and value not in prompt
    bridge.record_provider_input(gem, prompt)
    # Exact JSON payload argument passed to the official HTTP transport.
    import json, hashlib
    payload = {"contents":[{"role":"user","parts":[{"text":prompt}]}],"generationConfig":{"maxOutputTokens":1024}}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    bridge.record_runtime_payload_attestation(gem, {"payload_sha256":hashlib.sha256(canonical.encode()).hexdigest(), "payload_json":canonical})
    audit = bridge.seal_runtime_audit(user_prompt="runtime payload isolation test")
    assert audit["RUNTIME_HTTP_PAYLOAD_ATTESTED"] == "YES"
    assert audit["RUNTIME_HTTP_PAYLOAD_CONTAINS_VALUE"] == "NO"
    assert audit["RUNTIME_HTTP_PAYLOAD_CONTAINS_BRIDGE_KEY"] == "NO"
    assert audit["GEMINI_RECEIVED_SANITIZED_REPRESENTATION_ONLY"] == "PASS"
    assert audit["AUDIT_SEALED"] == "YES"
    assert audit["PRODUCTION_GATE"] == "PASS"


def test_hotfix118_tampered_post_seal_audit_fails_gate():
    ds = next(s for s in main.get_seats() if s.key == "deepseek")
    gem = next(s for s in main.get_seats() if s.key == "gemini")
    bridge = main.SharedContextBridge(request_id="rid118-b", round_no=1)
    value = "HOTFIX123-TAMPER-CANARY"
    bridge.append_agent_output(ds, _result(ds, f"BRIDGE_WRITE: BRIDGE_RESULT = {value}"))
    bridge.commit(gem); bridge.barrier()
    bridge.record_provider_input(gem, "sanitized")
    bridge.record_runtime_payload_attestation(gem, {"payload_sha256":"abc", "payload_json":"sanitized"})
    first = bridge.seal_runtime_audit(user_prompt="safe")
    assert first["PRODUCTION_GATE"] == "PASS"
    bridge._provider_input_prompts[2] = value
    tampered = bridge.transaction_audit(user_prompt="safe")
    assert tampered["PRODUCTION_GATE"] == "FAIL"


def test_hotfix118_release_identity():
    assert Path("VERSION.txt").read_text(encoding="utf-8").strip() == "V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE"
