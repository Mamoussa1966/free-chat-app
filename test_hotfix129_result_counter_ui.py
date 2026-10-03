from main import _ui_semantic_counters


def _r(status, seat, routed=False, configured=False, executed=False):
    return {
        "status": status,
        "seat": seat,
        "request_routed": routed,
        "model_candidates_configured": configured,
        "runtime_execution_events": ([{"execution_started": True}] if executed else []),
    }


def test_hotfix129_does_not_collapse_dispatch_rejected_into_failed():
    rows = [
        _r("SUCCESS", "gemini", True, True, True),
        _r("SUCCESS", "deepseek", True, True, True),
        _r("DISPATCH_REJECTED", "claude", True, True, False),
        _r("DISPATCH_REJECTED", "grok", True, True, False),
        _r("NOT_CONFIGURED", "chatgpt", False, False, False),
        _r("NOT_CONFIGURED", "kimi", False, False, False),
    ]
    c = _ui_semantic_counters(rows)
    assert c["configured"] == 4
    assert c["requested"] == 4
    assert c["executed"] == 2
    assert c["success"] == 2
    assert c["dispatch_rejected"] == 2
    assert c["provider_error"] == 0
    assert c["not_configured"] == 2
    assert c["cascade_attempts"] == 2


def test_hotfix129_runtime_execution_events_drive_executed_and_attempts():
    rows = [_r("SUCCESS", "gemini", True, True, True), _r("PROVIDER_ERROR", "grok", True, True, False)]
    rows[0]["runtime_execution_events"] = [
        {"execution_started": True}, {"execution_started": True}
    ]
    c = _ui_semantic_counters(rows)
    assert c["executed"] == 1
    assert c["cascade_attempts"] == 2
    assert c["success"] == 1
    assert c["provider_error"] == 1
