from main import _authoritative_request_metrics, _worker_failure


def test_worker_failure_never_creates_provider_attempt():
    class Seat:
        key = "claude"
        name = "Claude"
        label = "Claude"

    r = _worker_failure(Seat(), RuntimeError("boom"), {"claude": ("model-1",)}, "r1", 1)
    assert r["attempt_summaries"] == []
    assert r["attempt_telemetry"] == []
    assert r["runtime_execution_events"] == []
    assert r["attempted_models"] == []


def test_authoritative_counters_count_runtime_events_only():
    results = [
        {
            "seat": "gemini", "name": "Gemini", "request_id": "r1", "round": 1,
            "request_routed": True, "model_candidates_configured": True,
            "status": "SUCCESS", "content": "ok",
            "attempted_models": ["m1", "m2"],
            "runtime_execution_events": [
                {"execution_started": True, "attempt": 1, "model": "m1"},
                {"execution_started": True, "attempt": 2, "model": "m2"},
            ],
        },
        {
            "seat": "claude", "name": "Claude", "request_id": "r1", "round": 1,
            "request_routed": True, "model_candidates_configured": True,
            "status": "FAILED", "content": "",
            "attempted_models": [], "runtime_execution_events": [],
            "attempt_summaries": [{"attempt": 1, "classification": "API_ERROR"}],
        },
        {
            "seat": "grok", "name": "Grok", "request_id": "r1", "round": 1,
            "request_routed": False, "model_candidates_configured": True,
            "status": "FAILED", "content": "",
            "attempted_models": [], "runtime_execution_events": [],
        },
    ]
    events = [
        {"request_id": "r1", "event_type": "PROVIDER_RESULT", "round_id": 1,
         "provider": "Gemini", "metadata": {"runtime_execution": "true"}},
        {"request_id": "r1", "event_type": "PROVIDER_RESULT", "round_id": 1,
         "provider": "Gemini", "metadata": {"runtime_execution": "true"}},
    ]
    m = _authoritative_request_metrics("r1", results, events)
    assert m["configured_seats"] == 2
    assert m["requested_seats"] == 2
    assert m["executed_seats"] == 1
    assert m["successful_seats"] == 1
    assert m["total_cascade_attempts"] == 2
    assert m["provider_execution_events"] == 2
