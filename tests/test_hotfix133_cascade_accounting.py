from main import _authoritative_request_metrics, _ui_semantic_counters


def _result(seat, name, events, status="SUCCESS"):
    return {
        "seat": seat,
        "name": name,
        "request_id": "REQ-133",
        "round": 1,
        "request_routed": True,
        "model_candidates_configured": True,
        "status": status,
        "content": "ok" if status == "SUCCESS" else "",
        "attempted_models": [e.get("model") for e in events],
        "runtime_execution_events": events,
        "bridge_transaction_audit": {"BRIDGE_ID": "BR-133"},
    }


def _ev(attempt, model, classification, status, action):
    return {
        "execution_started": True,
        "attempt": attempt,
        "model": model,
        "request_id": "REQ-133",
        "round": 1,
        "classification": classification,
        "cascade_action": action,
        "status": status,
        "attempt_id": f"REQ-133:r1:a{attempt}",
    }


def test_hotfix133_counts_failed_runtime_attempts_authoritatively():
    gemini = _result("gemini", "Gemini", [
        _ev(1, "g1", "TRANSIENT_PROVIDER_ERROR", "FAILED", "CASCADE_CONTINUE"),
        _ev(2, "g2", "TRANSIENT_PROVIDER_ERROR", "FAILED", "CASCADE_CONTINUE"),
        _ev(3, "g3", "SUCCESS", "SUCCESS", "SUCCESS"),
    ])
    deepseek = _result("deepseek", "DeepSeek", [
        _ev(1, "d1", "SUCCESS", "SUCCESS", "SUCCESS"),
    ])
    not_configured_1 = {"seat":"chatgpt","request_id":"REQ-133","round":1,"request_routed":False,"model_candidates_configured":False,"status":"NOT_CONFIGURED","runtime_execution_events":[]}
    not_configured_2 = {"seat":"kimi","request_id":"REQ-133","round":1,"request_routed":False,"model_candidates_configured":False,"status":"NOT_CONFIGURED","runtime_execution_events":[]}
    events = [
        {"request_id":"REQ-133","round_id":1,"event_type":"PROVIDER_RESULT","status":"FAILED","metadata":{"runtime_execution":"true"}},
        {"request_id":"REQ-133","round_id":1,"event_type":"PROVIDER_RESULT","status":"FAILED","metadata":{"runtime_execution":"true"}},
        {"request_id":"REQ-133","round_id":1,"event_type":"PROVIDER_RESULT","status":"SUCCESS","metadata":{"runtime_execution":"true"}},
        {"request_id":"REQ-133","round_id":1,"event_type":"PROVIDER_RESULT","status":"SUCCESS","metadata":{"runtime_execution":"true"}},
    ]
    m = _authoritative_request_metrics("REQ-133", [gemini, deepseek, not_configured_1, not_configured_2], events)
    assert m["unique_request_ids"] == 1
    assert m["unique_bridge_ids"] == 1
    assert m["total_cascade_attempts"] == 4
    assert m["provider_execution_events"] == 2
    assert m["deepseek_round1_executions"] == 1


def test_hotfix133_ui_attempt_counter_uses_same_runtime_attempt_source():
    gemini = _result("gemini", "Gemini", [
        _ev(1, "g1", "TRANSIENT_PROVIDER_ERROR", "FAILED", "CASCADE_CONTINUE"),
        _ev(2, "g2", "TRANSIENT_PROVIDER_ERROR", "FAILED", "CASCADE_CONTINUE"),
        _ev(3, "g3", "SUCCESS", "SUCCESS", "SUCCESS"),
    ])
    deepseek = _result("deepseek", "DeepSeek", [_ev(1, "d1", "SUCCESS", "SUCCESS", "SUCCESS")])
    c = _ui_semantic_counters([gemini, deepseek])
    assert c["cascade_attempts"] == 4
    assert c["executed"] == 2
    assert c["success"] == 2
