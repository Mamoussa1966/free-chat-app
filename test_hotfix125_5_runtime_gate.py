import main
import production_platform


def _chat():
    return {"id":"c","messages":[],"request_ids":[],"request_records":[{"request_id":"648faf6e84f244bca6f286ed7a954d81","state":"COMPLETED","rounds":1,"rounds_executed":1,"results":[],"synthesis":{"status":"READY"},"request_metrics":{}}],"history_identity_ledger":[],"result_keys":[]}


def test_hotfix1255_detects_explicit_continuation_without_exact_phrase():
    c=_chat()
    rid, rec, is_cont=main._continuation_request_record("REQUEST_ID = 648faf6e84f244bca6f286ed7a954d81; continue the same runtime; no new request", c)
    assert is_cont and rid=="648faf6e84f244bca6f286ed7a954d81" and rec is not None


def test_hotfix1255_unknown_continuation_cannot_fall_through():
    c=_chat()
    rid, rec, is_cont=main._continuation_request_record("REQUEST_ID = deadbeefdeadbeefdeadbeefdeadbeef; continuation; do not create a new request", c)
    assert is_cont and rid=="deadbeefdeadbeefdeadbeefdeadbeef" and rec is None


def test_hotfix1255_security_rejects_bridge_leak_and_failed_transaction():
    c=_chat()
    c["request_records"][0]["results"]=[{"bridge_transaction_audit": {"WRITE":"FAIL","VALIDATE":"FAIL","COMMIT":"FAIL","BARRIER":"FAIL","READ":"FAIL","SCHEMA_VALIDATION":"FAIL","USER_PROMPT_CONTAINS_VALUE":"YES","GEMINI_INPUT_PROMPT_CONTAINS_VALUE":"YES","BRIDGE_STATE_CONTAINS_VALUE":"NO"}}]
    a=production_platform.security_audit([c])
    assert a["status"]=="FAIL"
    assert a["checks"]["BRIDGE_VALUES_NOT_IN_USER_PROMPT"] is False


def test_hotfix1255_no_provider_execution_path_for_continuation():
    c=_chat()
    try:
        main._run_council("x", c, 1, {}, [], {}, "m", "648faf6e84f244bca6f286ed7a954d81", continuation_request_id="648faf6e84f244bca6f286ed7a954d81")
    except RuntimeError as e:
        assert "READ_ONLY" in str(e)
    else:
        raise AssertionError("continuation reached orchestrator execution")
