import json

from v23_audit_export import build_v23_audit_export, serialize_v23_audit_export


def test_full_export_contains_all_runtime_audit_sections_and_no_provider_secret_fields():
    payload = build_v23_audit_export(
        platform_audit={"conversation_runtime_audit": "PASS"},
        final_closure_audit={"overall_authoritative_status": "PASS"},
        security_audit={"api_keys_in_state": "NO"},
        health_snapshot=[{"provider": "Gemini", "status": "READY"}],
        production_core_report={"passed": True},
        production_core_code=0,
    )
    raw = serialize_v23_audit_export(payload)
    decoded = json.loads(raw)
    assert decoded["schema"] == "v23-platform-audit-export/v1"
    assert decoded["platform_audit"]["conversation_runtime_audit"] == "PASS"
    assert decoded["final_closure_audit"]["overall_authoritative_status"] == "PASS"
    assert decoded["security_audit"]["api_keys_in_state"] == "NO"
    assert decoded["provider_health_snapshot"][0]["provider"] == "Gemini"
    assert decoded["production_core"]["code"] == 0
    assert "authorization" not in raw.lower()
    assert "secret_value_example" not in raw.lower()


def test_export_preserves_not_proven_without_relabeling():
    raw = serialize_v23_audit_export(
        build_v23_audit_export(
            platform_audit={"overall_authoritative_status": "NOT_PROVEN"},
        )
    )
    decoded = json.loads(raw)
    assert decoded["platform_audit"]["overall_authoritative_status"] == "NOT_PROVEN"
