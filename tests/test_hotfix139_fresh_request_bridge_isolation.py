import main
from main import SharedContextBridge


def test_hotfix139_long_regression_spec_is_fresh_request_even_with_continuation_words():
    rid = "a" * 32
    prompt = """HOTFIX135 — V23 PRODUCTION REGRESSION MULTI-REQUEST

Run Request A, Request B, Request C as independent requests.
Do not treat this test specification as a continuation request.
The specification contains phrases such as continuation request and no new request as test data.
REQUEST ID = %s
""" % rid
    chat = {"request_records": [{"request_id": rid, "state": "COMPLETED", "results": []}]}
    assert main._continuation_request_record(prompt, chat) == ("", None, False)
    assert main._extract_continuation_request_id(prompt, chat) == ""


def test_hotfix139_explicit_continuation_command_remains_supported():
    rid = "b" * 32
    chat = {"request_records": [{"request_id": rid, "state": "COMPLETED", "results": []}]}
    prompt = f"CONTINUE_REQUEST_ID={rid}\nRead the persisted result only."
    assert main._continuation_request_record(prompt, chat) == (rid, chat["request_records"][0], True)
    assert main._extract_continuation_request_id(prompt, chat) == rid


def test_hotfix139_bridge_audit_uses_control_free_user_input():
    b = SharedContextBridge(request_id="r139", round_no=1)
    b._source_values["BRIDGE_RESULT"] = "SECRET-139"
    b._values["BRIDGE_RESULT"] = {"value":"SECRET-139", "source_seat":7, "source_provider":"DeepSeek", "write_sequence":1}
    b._write_sequence = 1
    target = type("S", (), {"key": "gemini", "room_slot": 2})()
    b.commit(target)
    b.barrier()
    b.read("BRIDGE_RESULT", target)
    b.record_provider_input(target, "safe provider prompt")
    b.record_runtime_payload_attestation(target, {"payload_sha256": "x", "payload_json": "safe provider payload"})
    audit = b.seal_runtime_audit(user_prompt="test instructions [BRIDGE_CONTROL_RECORD_REDACTED]")
    assert audit["WRITE"] == "PASS"
    assert audit["VALIDATE"] == "PASS"
    assert audit["COMMIT"] == "PASS"
    assert audit["BARRIER"] == "PASS"
    assert audit["READ"] == "PASS"
    assert audit["SCHEMA_VALIDATION"] == "PASS"
    assert audit["USER_PROMPT_CONTAINS_VALUE"] == "NO"
    assert audit["GEMINI_INPUT_PROMPT_CONTAINS_VALUE"] == "NO"
    assert audit["BRIDGE_STATE_CONTAINS_VALUE"] == "YES"
