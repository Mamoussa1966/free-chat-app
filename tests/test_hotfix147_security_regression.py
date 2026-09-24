from main import _authoritative_ui_projection, _format_authoritative_counter_summary
from production_platform import security_audit, conversation_persistence_audit


def _record():
    rid = "HF147-RID"
    return {
        "request_id": rid,
        "results": [
            {"status": "SUCCESS", "seat": "gemini"},
            {"status": "SUCCESS", "seat": "deepseek"},
            {"status": "DISPATCH_REJECTED", "seat": "claude"},
            {"status": "DISPATCH_REJECTED", "seat": "grok"},
            {"status": "NOT_CONFIGURED", "seat": "chatgpt"},
            {"status": "NOT_CONFIGURED", "seat": "kimi"},
        ],
        "request_metrics": {
            "configured_seats": 4, "requested_seats": 4, "executed_seats": 2,
            "successful_seats": 2, "total_cascade_attempts": 2,
        },
    }


def test_security_allows_empty_redacted_raw_payload_field():
    report = security_audit([{"request_records": [{"raw_provider_payload": "", "request_id": "r"}]}])
    assert report["checks"]["NO_RAW_PROVIDER_PAYLOADS_IN_HISTORY"] is True


def test_security_rejects_nonempty_raw_payload_value():
    report = security_audit([{"request_records": [{"raw_provider_payload": {"body": "secret-provider-response"}}]}])
    assert report["checks"]["NO_RAW_PROVIDER_PAYLOADS_IN_HISTORY"] is False


def test_persistence_audit_uses_values_not_field_names():
    safe = {"id": "c", "messages": [], "request_records": [{"raw_provider_payload": ""}]}
    assert conversation_persistence_audit(safe, "")["forbidden_data"]["RAW_PROVIDER_PAYLOADS"] is False
    unsafe = {"id": "c", "messages": [], "request_records": [{"raw_provider_payload": "x"}]}
    assert conversation_persistence_audit(unsafe, "")["forbidden_data"]["RAW_PROVIDER_PAYLOADS"] is True


def test_hotfix130_projection_restored_and_authoritative():
    c = _authoritative_ui_projection({"request_records": [_record()]}, "HF147-RID")
    assert (c["configured"], c["requested"], c["executed"], c["success"], c["dispatch_rejected"], c["not_configured"], c["cascade_attempts"]) == (4, 4, 2, 2, 2, 2, 2)
    summary = _format_authoritative_counter_summary(c)
    assert "DISPATCH_REJECTED 2" in summary and "NOT_CONFIGURED 2" in summary
    assert "failed" not in summary.lower() and "successful" not in summary.lower()
