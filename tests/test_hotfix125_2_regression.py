import main
from main import SharedContextBridge
from production_platform import build_v23_platform_audit


def test_continuation_requires_persisted_request_and_never_allocates_id():
    chat = {"request_records": [{"request_id": "a"*32, "results": [], "state": "COMPLETED"}]}
    assert main._extract_continuation_request_id("continue same request with Request ID `" + "a"*32 + "`", chat) == "a"*32
    assert main._extract_continuation_request_id("continue same request with Request ID `" + "b"*32 + "`", chat) == ""


def test_bridge_user_control_is_removed_and_state_is_application_owned():
    sanitized, controls = main._extract_bridge_control_values("run test\nBRIDGE_RESULT = SECRET-7319")
    assert "SECRET-7319" not in sanitized
    assert "BRIDGE_RESULT" not in sanitized
    assert controls == [("BRIDGE_RESULT", "SECRET-7319")]
    b = SharedContextBridge(request_id="r1", round_no=1)
    b.seed_application_state("BRIDGE_RESULT", "SECRET-7319")
    b.commit(type("S", (), {"room_slot": 2})())
    b.barrier()
    prompt = b.prompt_snapshot(type("S", (), {"key":"gemini", "room_slot":2})())
    assert "SECRET-7319" not in prompt
    assert "BRIDGE_RESULT" not in prompt
    assert b.application_owned_state()["values"]["BRIDGE_RESULT"]["value"] == "SECRET-7319"


def test_full_audit_fails_on_bridge_isolation_runtime_failure():
    c={"id":"s","messages":[{"role":"user","content":"x","request_id":"r1"}],"request_records":[{
        "request_id":"r1","rounds_executed":1,"results":[{"status":"SUCCESS","content":"ok","request_id":"r1","round":1,
        "bridge_transaction_audit":{"BRIDGE_ID":"b1","WRITE":"FAIL","USER_PROMPT_CONTAINS_VALUE":"YES","GEMINI_INPUT_PROMPT_CONTAINS_VALUE":"YES","BRIDGE_STATE_CONTAINS_VALUE":"NO"}}],
        "request_metrics":{"unique_request_ids":1},"synthesis":{"status":"READY"}}],"history_identity_ledger":[["r1",1,"deepseek"]]}
    ctx={"chars":1,"digest":"x"}; health=[{"status":"READY"}]; sec={"status":"PASS"}; reg={"gate":"PASS"}
    r=build_v23_platform_audit(c,"r1",ctx,health,sec,reg)
    assert r["status"] == "FAIL"
    assert r["bridge_isolation"]["status"] == "FAIL"
