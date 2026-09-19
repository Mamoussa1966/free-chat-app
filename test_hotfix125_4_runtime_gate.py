import main
from production_platform import build_v23_platform_audit

RID = "648faf6e84f244bca6f286ed7a954d81"

def test_exact_request_id_continuation_phrase_is_detected_before_allocation():
    chat={"request_records":[{"request_id":RID,"state":"COMPLETED","results":[],"synthesis":{}}]}
    requested, record, cont = main._continuation_request_record(
        f"استكمال نفس الطلب — REQUEST_ID = {RID} — لا Request جديد ولا Provider ولا Cascade ولا Bridge", chat)
    assert cont is True
    assert requested == RID
    assert record["request_id"] == RID

def test_continuation_unknown_id_is_hard_rejected():
    chat={"request_records":[]}
    requested, record, cont = main._continuation_request_record(
        f"CONTINUATION REQUEST_ID = {RID}", chat)
    assert cont is True and requested == RID and record is None

def test_runtime_audit_has_explicit_continuation_gate():
    c={"id":"s","messages":[],"request_records":[{"request_id":RID,"results":[],"synthesis":{}}],"audit_events":[{"type":"CONTINUATION_GATE","requested_request_id":RID,"mode":"READ_ONLY","actual_request_id":RID,"provider_execution":0,"cascade":0,"new_round":0,"new_bridge":0}],"history_identity_ledger":[] }
    r=build_v23_platform_audit(c,RID,{"chars":1,"digest":"x"},[{"status":"READY"}],{"status":"PASS"},{"gate":"PASS"})
    assert r["continuation_runtime_gate"]["status"] == "PASS"

def test_runtime_audit_fails_continuation_gate_if_provider_executed():
    c={"id":"s","messages":[],"request_records":[{"request_id":RID,"results":[],"synthesis":{}}],"audit_events":[{"type":"CONTINUATION_GATE","requested_request_id":RID,"mode":"READ_ONLY","actual_request_id":RID,"provider_execution":1,"cascade":1,"new_round":0,"new_bridge":1}],"history_identity_ledger":[] }
    r=build_v23_platform_audit(c,RID,{"chars":1,"digest":"x"},[{"status":"READY"}],{"status":"PASS"},{"gate":"PASS"})
    assert r["continuation_runtime_gate"]["status"] == "FAIL"
    assert r["status"] == "FAIL"
