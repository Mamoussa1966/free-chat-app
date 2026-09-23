import main
from production_platform import build_v23_platform_audit

RID = "648faf6e84f244bca6f286ed7a954d81"

def _completed_chat():
    return {"id":"c","messages":[],"request_records":[{"request_id":RID,"state":"COMPLETED","rounds":1,"rounds_executed":1,"results":[],"synthesis":{"status":"READY"}}],"audit_events":[],"history_identity_ledger":[],"result_keys":[]}

def test_hotfix126_persisted_id_is_continuation_even_without_word_continuation():
    chat = _completed_chat()
    prompt = f"REQUEST_ID = {RID}; لا تنشئ Request جديد ولا Round جديد ولا Bridge جديد."
    requested, record, is_cont = main._continuation_request_record(prompt, chat)
    assert is_cont is True
    assert requested == RID
    assert record is not None and record["request_id"] == RID

def test_hotfix126_completed_request_id_cannot_allocate_new_request():
    chat = _completed_chat()
    requested, record, is_cont = main._continuation_request_record(f"REQUEST ID: {RID}", chat)
    assert is_cont is True and requested == RID and record is not None

def test_hotfix126_unknown_id_still_requires_continuation_marker():
    chat = _completed_chat()
    unknown = "deadbeefdeadbeefdeadbeefdeadbeef"
    requested, record, is_cont = main._continuation_request_record(f"REQUEST_ID={unknown}", chat)
    assert is_cont is False and requested == "" and record is None

def test_hotfix126_full_audit_rejects_two_bridge_ids():
    chat = _completed_chat()
    chat["request_records"][0]["results"] = [
        {"bridge_transaction_audit":{"BRIDGE_ID":"b1","WRITE":"PASS","VALIDATE":"PASS","COMMIT":"PASS","BARRIER":"PASS","READ":"PASS","SCHEMA_VALIDATION":"PASS","USER_PROMPT_CONTAINS_VALUE":"NO","GEMINI_INPUT_PROMPT_CONTAINS_VALUE":"NO","BRIDGE_STATE_CONTAINS_VALUE":"YES"}},
        {"bridge_transaction_audit":{"BRIDGE_ID":"b2","WRITE":"PASS","VALIDATE":"PASS","COMMIT":"PASS","BARRIER":"PASS","READ":"PASS","SCHEMA_VALIDATION":"PASS","USER_PROMPT_CONTAINS_VALUE":"NO","GEMINI_INPUT_PROMPT_CONTAINS_VALUE":"NO","BRIDGE_STATE_CONTAINS_VALUE":"YES"}},
    ]
    r = build_v23_platform_audit(chat, RID, {"chars":1,"digest":"x"}, [{"status":"READY"}], {"status":"PASS"}, {"status":"PASS"})
    assert r["bridge_isolation"]["status"] == "FAIL"
    assert r["status"] == "FAIL"
    assert r["bridge_isolation"]["unique_persisted_bridge_ids"] == ["b1","b2"]


def test_hotfix126_production_gate_rejects_non_authoritative_round_2_label():
    from production_platform import build_v23_platform_audit
    chat = {
        "id": "c", "conversation_id": "c", "session_id": "s",
        "messages": [], "request_records": [{"request_id":"rid","state":"COMPLETED","results":[]}],
        "conversation_record": {
            "rounds": [
                {"round_id":"c:rid1:r1","round":1,"round_identity_contract":"V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1"},
                {"round_id":"c:rid2:r1","round":2,"round_identity_contract":"V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1"},
            ]
        },
    }
    r = build_v23_platform_audit(chat, "rid", {"chars":0,"digest":"x"}, [{"status":"READY"}], {"status":"PASS"}, {"gate":"PASS"})
    assert r["round_identity_gate"]["status"] == "FAIL"
    assert r["status"] == "FAIL"


def test_hotfix126_production_gate_proves_real_round_2_from_ledger():
    from production_platform import build_v23_platform_audit
    chat = {
        "id": "c", "conversation_id": "c", "session_id": "s",
        "messages": [], "request_records": [{"request_id":"rid","state":"COMPLETED","results":[]}],
        "conversation_record": {
            "rounds": [
                {"round_id":"c:rid1:r1","round":1,"round_identity_contract":"V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1"},
                {"round_id":"c:rid2:r2","round":2,"round_identity_contract":"V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1"},
            ]
        },
    }
    r = build_v23_platform_audit(chat, "rid", {"chars":0,"digest":"x"}, [{"status":"READY"}], {"status":"PASS"}, {"gate":"PASS"})
    assert r["round_identity_gate"]["status"] == "PASS"
