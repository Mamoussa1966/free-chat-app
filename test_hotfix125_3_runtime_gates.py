import main
from production_platform import build_v23_platform_audit


def test_continuation_loads_persisted_record_and_never_allocates_identity():
    rid = "648faf6e84f244bca6f286ed7a954d81"
    chat = {"request_records": [{"request_id": rid, "state": "COMPLETED", "results": [{"status": "SUCCESS"}], "synthesis": {"status": "READY"}}]}
    requested, record, cont = main._continuation_request_record(f"CONTINUATION REQUEST ID: {rid}", chat)
    assert cont is True
    assert requested == rid
    assert record["request_id"] == rid
    assert main._extract_continuation_request_id(f"continue Request ID: {rid}", chat) == rid


def test_continuation_unknown_id_is_rejected_before_allocation():
    chat = {"request_records": []}
    requested, record, cont = main._continuation_request_record("continue Request ID: " + "a"*32, chat)
    assert cont is True and requested == "a"*32 and record is None


def test_run_council_hard_rejects_continuation_execution():
    rid = "r-cont"
    chat = {"request_records": [{"request_id": rid, "state": "COMPLETED", "results": []}]}
    try:
        main._run_council("continue", chat, 1, {}, [], {}, "msg", rid, continuation_request_id=rid)
    except RuntimeError as exc:
        assert "READ_ONLY" in str(exc)
    else:
        raise AssertionError("continuation entered orchestrator")


def test_bridge_control_is_absent_from_provider_boundary():
    sanitized, controls = main._extract_bridge_control_values("run test BRIDGE_RESULT = SECRET-7319")
    assert controls == [("BRIDGE_RESULT", "SECRET-7319")]
    assert "BRIDGE_RESULT" not in sanitized
    assert "SECRET-7319" not in sanitized
    main._assert_provider_boundary(sanitized, "ordinary sanitized context", controls)


def test_runtime_audit_cannot_pass_on_request_id_mismatch():
    c={"id":"s","messages":[{"role":"user","content":"x","request_id":"actual"}],"request_records":[{"request_id":"actual","rounds_executed":1,"results":[],"request_metrics":{},"synthesis":{"status":"READY"}}],"history_identity_ledger":[]}
    r=build_v23_platform_audit(c,"requested",{"chars":1,"digest":"x"},[{"status":"READY"}],{"status":"PASS"},{"gate":"PASS"})
    assert r["status"] == "FAIL"


def test_runtime_bridge_audit_must_be_no_no_and_application_owned():
    c={"id":"s","messages":[{"role":"user","content":"x","request_id":"r1"}],"request_records":[{"request_id":"r1","rounds_executed":1,"results":[{"status":"SUCCESS","content":"ok","request_id":"r1","round":1,"attempt_summaries":[{"attempt":1}],"bridge_transaction_audit":{"BRIDGE_ID":"b1","WRITE":"PASS","VALIDATE":"PASS","COMMIT":"PASS","BARRIER":"PASS","READ":"PASS","SCHEMA_VALIDATION":"PASS","USER_PROMPT_CONTAINS_VALUE":"NO","GEMINI_INPUT_PROMPT_CONTAINS_VALUE":"NO","BRIDGE_STATE_CONTAINS_VALUE":"YES"}}],"request_metrics":{"unique_request_ids":1,"request_id":"r1"},"synthesis":{"status":"READY"},"application_owned_bridge_state":{"values":{"BRIDGE_RESULT":{"value":"SECRET"}}}}],"history_identity_ledger":[]}
    r=build_v23_platform_audit(c,"r1",{"chars":1,"digest":"x"},[{"status":"READY"}],{"status":"PASS"},{"gate":"PASS"})
    assert r["status"] == "PASS"
    assert r["bridge_isolation"]["checks"]["USER_PROMPT_ISOLATED"] is True
    assert r["bridge_isolation"]["checks"]["GEMINI_INPUT_ISOLATED"] is True
