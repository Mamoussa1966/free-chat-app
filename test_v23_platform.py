from production_platform import compact_context, synthesize_council_results, security_audit, provider_health_snapshot, CORE_BASELINE


def test_context_compaction_is_bounded_and_identity_aware():
    text, meta = compact_context([{"role":"user","request_id":"r1","content":"x"*100000}], max_chars=6000)
    assert len(text) <= 6000
    assert meta["digest"]


def test_synthesis_is_application_owned():
    result = synthesize_council_results([
        {"status":"SUCCESS","name":"Gemini","request_id":"r1","round":1,"content":"ok"},
        {"status":"FAILED","name":"Grok","request_id":"r1","round":1},
    ])
    assert result["status"] == "READY"
    assert result["source_request_ids"] == ["r1"]
    assert result["composition"] == "APPLICATION_OWNED_RESULT_SET"


def test_security_audit_does_not_break_baseline_contract():
    report = security_audit([{"messages":[{"role":"assistant","content":"normal"}]}])
    assert report["status"] == "PASS"
    assert report["checks"]["REQUEST_ID_AUTHORITY_PRESERVED"]
    assert CORE_BASELINE.endswith("LIVE-CASCADE")


def test_provider_health_uses_existing_configuration_only():
    class S:
        key="gemini"; name="Gemini"
    rows = provider_health_snapshot([S()], {"gemini": "configured"}, {"gemini": ("model-a",)})
    assert rows[0]["status"] == "READY"
    assert rows[0]["free_models"] == 1
