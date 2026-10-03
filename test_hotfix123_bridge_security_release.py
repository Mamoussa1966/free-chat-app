from pathlib import Path
import json
import main
from release_identity import deployed_release_identity, assert_deployed_release_identity


def _seats():
    seats = main.get_seats()
    return next(s for s in seats if s.key == "deepseek"), next(s for s in seats if s.key == "gemini")


def test_hotfix123_deployed_identity_is_frozen_and_not_mutated():
    r = assert_deployed_release_identity()
    assert r["gate"] == "PASS"
    assert r["status"] == "FROZEN_BASELINE"
    assert r["observed"]["provider_core"].startswith("V22.1-HOTFIX123.2-")
    assert r["observed"]["hotfix_release"].startswith("V23.0-HOTFIX144-")
    assert r["observed"]["platform_release"].startswith("V24.0-HOTFIX145-")


def test_hotfix123_bridge_positive_security_proof_is_application_owned():
    ds, gem = _seats()
    bridge = main.SharedContextBridge(request_id="RID-HF123", round_no=1)
    value = "HOTFIX123-CANARY-7Q9X"
    bridge.seed_application_state("BRIDGE_RESULT", value, source="DeepSeek", source_seat=7)
    bridge.commit(gem)
    bridge.barrier()
    bridge.read("BRIDGE_RESULT", gem)
    bridge.record_provider_input(gem, bridge.prompt_snapshot(gem))
    bridge.record_runtime_payload_attestation(gem, {"payload_json":"{\"input\":\"sanitized\"}", "payload_sha256":"attested"})
    audit = bridge.transaction_audit(user_prompt="TRANSACTIONAL BRIDGE ISOLATION")
    assert audit["WRITE"] == "PASS"
    assert audit["VALIDATE"] == "PASS"
    assert audit["COMMIT"] == "PASS"
    assert audit["BARRIER"] == "PASS"
    assert audit["READ"] == "PASS"
    assert audit["SCHEMA_VALIDATION"] == "PASS"
    assert audit["MATCH"] == "PASS"
    assert audit["USER_PROMPT_CONTAINS_VALUE"] == "NO"
    assert audit["GEMINI_INPUT_PROMPT_CONTAINS_VALUE"] == "NO"
    assert audit["BRIDGE_STATE_CONTAINS_VALUE"] == "YES"


def test_hotfix123_bridge_negative_target_prompt_leak_fails():
    ds, gem = _seats()
    bridge = main.SharedContextBridge(request_id="RID-HF123-NEG", round_no=1)
    value = "HOTFIX123-NEGATIVE-CANARY"
    bridge.seed_application_state("BRIDGE_RESULT", value, source="DeepSeek", source_seat=7)
    bridge.commit(gem); bridge.barrier(); bridge.read("BRIDGE_RESULT", gem)
    bridge.record_provider_input(gem, "LEAK " + value)
    bridge.record_runtime_payload_attestation(gem, {"payload_json":json.dumps({"input":"LEAK " + value}), "payload_sha256":"attested"})
    audit = bridge.transaction_audit(user_prompt="clean")
    assert audit["GEMINI_INPUT_PROMPT_CONTAINS_VALUE"] == "YES"
    assert audit["RUNTIME_HTTP_PAYLOAD_CONTAINS_VALUE"] == "YES"
    assert audit["GEMINI_RECEIVED_SANITIZED_REPRESENTATION_ONLY"] == "FAIL"


def test_hotfix123_no_secret_is_rendered_by_release_identity():
    text = Path("RELEASE_IDENTITY.json").read_text(encoding="utf-8")
    assert "API_KEY" not in text
    assert "Authorization" not in text

