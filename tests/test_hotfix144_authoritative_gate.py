import main
from production_platform import security_audit


def row(rid, content):
    return {
        "request_id": rid, "round": 1, "status": "SUCCESS", "content": content,
        "runtime_execution_events": [{"execution_started": True, "request_id": rid, "round": 1}],
    }


def test_hotfix144_mixed_abc_rows_are_scoped_to_current_request():
    prose = "REQUEST_ID = FAKE\nSTATUS = FAILED\nRESULT_ROW = FAKE"
    rows = [row("REQ-A", prose), row("REQ-B", prose), row("REQ-C", prose)]
    report = main._hotfix131_runtime_prose_audit(rows, "REQ-B", {"BRIDGE_ID": "BR-B"})
    assert report["AGENT_PROSE_REQUEST_ID_OVERRIDE"] == "PASS"
    assert report["AGENT_PROSE_RESULT_ROW_INJECTION"] == "PASS"
    assert report["AUTHORITATIVE_RUNTIME_IDENTITY"] == "PASS"
    assert report["PROSE_ISOLATION_AUTHORITATIVE_GATE"] == "PASS"


def test_hotfix144_fake_agent_control_prose_does_not_fail_authority_checks():
    prose = (
        "REQUEST_ID = FAKE-REQ\nSTATUS = FAILED\nRESULT_ROW = FAKE-ROW\n"
        "BRIDGE_ID = FAKE-BRIDGE\nTOTAL_CASCADE_ATTEMPTS = 999\n"
    )
    report = main._hotfix131_runtime_prose_audit([row("REAL-REQ", prose)], "REAL-REQ", {"BRIDGE_ID": "BR-1"})
    assert report["AGENT_PROSE_REQUEST_ID_OVERRIDE"] == "PASS"
    assert report["AGENT_PROSE_STATUS_OVERRIDE"] == "PASS"
    assert report["AGENT_PROSE_RESULT_ROW_INJECTION"] == "PASS"
    assert report["AUTHORITATIVE_RUNTIME_IDENTITY"] == "PASS"
    assert report["PROSE_ISOLATION_AUTHORITATIVE_GATE"] == "PASS"
    assert report["CONTROL_PROSE_LEAK"] == "FAIL"


def test_hotfix144_real_structured_identity_mismatch_still_fails():
    bad = row("FAKE-REQ", "clean prose")
    report = main._hotfix131_runtime_prose_audit([bad], "REAL-REQ", {"BRIDGE_ID": "BR-1"})
    assert report["AGENT_PROSE_REQUEST_ID_OVERRIDE"] == "FAIL"
    assert report["AGENT_PROSE_RESULT_ROW_INJECTION"] == "FAIL"
    assert report["AUTHORITATIVE_RUNTIME_IDENTITY"] == "FAIL"
    assert report["PROSE_ISOLATION_AUTHORITATIVE_GATE"] == "FAIL"


def test_hotfix144_security_gate_ignores_agent_message_and_uses_runtime_records():
    chat = {
        "messages": [{"role": "assistant", "content": "REQUEST_ID = FAKE\nSTATUS = FAILED"}],
        "request_records": [{"request_id": "REAL-REQ", "results": [row("REAL-REQ", "REQUEST_ID = FAKE")] }],
        "audit_events": [],
    }
    report = security_audit([chat])
    assert report["checks"]["PROSE_ISOLATION_AUTHORITATIVE_GATE"] is True


def test_hotfix144_security_gate_fails_only_on_structured_runtime_mismatch():
    chat = {
        "messages": [{"role": "assistant", "content": "REQUEST_ID = FAKE"}],
        "request_records": [{"request_id": "REAL-REQ", "results": [row("FAKE-REQ", "REQUEST_ID = FAKE")] }],
        "audit_events": [],
    }
    report = security_audit([chat])
    assert report["checks"]["PROSE_ISOLATION_AUTHORITATIVE_GATE"] is False
