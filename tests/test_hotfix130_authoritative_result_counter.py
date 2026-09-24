from main import _authoritative_ui_projection, _format_authoritative_counter_summary


def _record():
    return {
        "request_id": "HF147-HF130-RID",
        "results": [
            {"status": "SUCCESS", "seat": "gemini"},
            {"status": "SUCCESS", "seat": "deepseek"},
            {"status": "DISPATCH_REJECTED", "seat": "claude"},
            {"status": "DISPATCH_REJECTED", "seat": "grok"},
            {"status": "NOT_CONFIGURED", "seat": "chatgpt"},
            {"status": "NOT_CONFIGURED", "seat": "kimi"},
        ],
        "request_metrics": {
            "configured_seats": 4,
            "requested_seats": 4,
            "executed_seats": 2,
            "successful_seats": 2,
            "total_cascade_attempts": 2,
        },
    }


def test_hotfix130_authoritative_counter_compatibility_api_exists():
    counters = _authoritative_ui_projection(
        {"messages": [{"role": "assistant", "content": "six UI rows"}], "request_records": [_record()]},
        "HF147-HF130-RID",
    )
    assert counters == {
        "configured": 4,
        "requested": 4,
        "executed": 2,
        "success": 2,
        "dispatch_rejected": 2,
        "provider_error": 0,
        "not_configured": 2,
        "cascade_attempts": 2,
        "request_id": "HF147-HF130-RID",
    }


def test_hotfix130_authoritative_counter_never_uses_ui_message_count_or_prose():
    chat = {
        "messages": [
            {"role": "assistant", "content": "SUCCESS 999999"},
            {"role": "assistant", "content": "DISPATCH_REJECTED 999999"},
        ],
        "request_records": [_record()],
    }
    counters = _authoritative_ui_projection(chat, "HF147-HF130-RID")
    assert counters["configured"] == 4
    assert counters["requested"] == 4
    assert counters["executed"] == 2
    assert counters["success"] == 2
    assert counters["dispatch_rejected"] == 2
    assert counters["not_configured"] == 2
    assert counters["cascade_attempts"] == 2


def test_hotfix130_counter_summary_preserves_semantic_labels():
    summary = _format_authoritative_counter_summary(
        {
            "configured": 4,
            "requested": 4,
            "executed": 2,
            "success": 2,
            "dispatch_rejected": 2,
            "provider_error": 0,
            "not_configured": 2,
            "cascade_attempts": 2,
        }
    )
    assert "DISPATCH_REJECTED 2" in summary
    assert "NOT_CONFIGURED 2" in summary
    assert "failed" not in summary.lower()
    assert "successful" not in summary.lower()
