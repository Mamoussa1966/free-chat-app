from types import SimpleNamespace

import main


def _seats():
    return [
        SimpleNamespace(key="deepseek", name="DeepSeek", label="DeepSeek", room_slot=7),
        SimpleNamespace(
            key="cloudflare_workers_ai",
            name="Cloudflare Workers AI",
            label="Cloudflare Workers AI",
            room_slot=8,
        ),
        SimpleNamespace(key="gemini", name="Gemini", label="Gemini", room_slot=2),
    ]


def _fake_success(seat, round_no, request_id, model):
    return {
        "seat": seat.key,
        "name": seat.name,
        "label": seat.label,
        "status": "SUCCESS",
        "mode": "official",
        "model": model,
        "executed_model": model,
        "provider_reported_model": model,
        "content": "TEST_PROVIDER_OK",
        "error": None,
        "latency": 0.01,
        "successful_attempt_latency": 0.01,
        "attempted_models": [model],
        "attempt_diagnostics": [],
        "attempt_summaries": [],
        "attempt_telemetry": [
            {
                "provider": seat.name,
                "attempt": 1,
                "model": model,
                "status_code": 200,
                "classification": "SUCCESS",
                "retryable": False,
                "execution_time": 0.01,
                "request_id": request_id,
                "attempt_id": f"{request_id}:r{round_no}:a1",
                "round": round_no,
                "final_result": "SUCCESS",
                "cascade_action": "SUCCESS",
                "cascade_reason": "",
            }
        ],
        "runtime_execution_events": [
            {
                "provider": seat.key,
                "attempt": 1,
                "model": model,
                "status": "SUCCESS",
                "execution_started": True,
                "execution_time": 0.01,
                "status_code": 200,
                "request_id": request_id,
                "round": round_no,
                "attempt_id": f"{request_id}:r{round_no}:a1",
            }
        ],
        "official_authenticated": True,
        "request_id": request_id,
        "round": round_no,
    }


def _run_test_round(monkeypatch, fake_call):
    seats = _seats()
    monkeypatch.setattr(main, "get_seats", lambda: seats)
    monkeypatch.setattr(main, "_render_live_cascade_telemetry", lambda result: None)
    credentials = {seat.key: "TEST_CREDENTIAL" for seat in seats}
    candidates = {
        "deepseek": ("deepseek-test-model",),
        "cloudflare_workers_ai": ("@cf/zai-org/glm-4.7-flash",),
        "gemini": ("gemini-test-model",),
    }
    chat = {"messages": []}
    monkeypatch.setattr(main, "call_seat", fake_call)
    results = main._run_round(
        "normal Council round",
        chat,
        12,
        credentials,
        [],
        candidates,
        "message-test-12",
        None,
        "request-test-12",
    )
    return results


def test_normal_round_dispatches_cloudflare_before_gemini_and_binds_round_identity(monkeypatch):
    calls = []

    def fake_call(
        seat, user_prompt, shared_context, round_no, local_fallback,
        credential, attachments=None, model_candidates=None, deadline=None, request_id="",
    ):
        calls.append(seat.key)
        model = (model_candidates or ("test-model",))[0]
        return _fake_success(seat, round_no, request_id, model)

    results = _run_test_round(monkeypatch, fake_call)

    assert calls == ["deepseek", "cloudflare_workers_ai", "gemini"]
    cloudflare = next(row for row in results if row["seat"] == "cloudflare_workers_ai")
    assert cloudflare["status"] == "SUCCESS"
    assert cloudflare["executed_model"] == "@cf/zai-org/glm-4.7-flash"
    assert cloudflare["attempted_models"] == ["@cf/zai-org/glm-4.7-flash"]
    assert cloudflare["request_id"] == "request-test-12"
    assert cloudflare["round"] == 12
    assert cloudflare["runtime_execution_events"][0]["status_code"] == 200


def test_post_provider_handoff_exception_preserves_cloudflare_attempt_evidence(monkeypatch):
    def fake_call(
        seat, user_prompt, shared_context, round_no, local_fallback,
        credential, attachments=None, model_candidates=None, deadline=None, request_id="",
    ):
        model = (model_candidates or ("test-model",))[0]
        return _fake_success(seat, round_no, request_id, model)

    original = main.SharedContextBridge.append_agent_output

    def fail_cloudflare_handoff(self, seat, result):
        if seat.key == "cloudflare_workers_ai":
            raise RuntimeError("synthetic bridge handoff failure")
        return original(self, seat, result)

    monkeypatch.setattr(main.SharedContextBridge, "append_agent_output", fail_cloudflare_handoff)
    results = _run_test_round(monkeypatch, fake_call)

    cloudflare = next(row for row in results if row["seat"] == "cloudflare_workers_ai")
    assert cloudflare["status"] == "PROVIDER_ERROR"
    assert cloudflare["failure_stage"] == "BRIDGE_OUTPUT_HANDOFF"
    assert cloudflare["orchestration_error_type"] == "RuntimeError"
    assert cloudflare["execution_started"] is True
    assert cloudflare["attempted_models"] == ["@cf/zai-org/glm-4.7-flash"]
    assert cloudflare["runtime_execution_events"][0]["status_code"] == 200
    assert cloudflare["request_id"] == "request-test-12"
    assert cloudflare["round"] == 12


def test_provider_call_exception_reports_stage_without_fabricating_attempt(monkeypatch):
    def fake_call(
        seat, user_prompt, shared_context, round_no, local_fallback,
        credential, attachments=None, model_candidates=None, deadline=None, request_id="",
    ):
        if seat.key == "cloudflare_workers_ai":
            raise RuntimeError("synthetic call boundary failure")
        model = (model_candidates or ("test-model",))[0]
        return _fake_success(seat, round_no, request_id, model)

    results = _run_test_round(monkeypatch, fake_call)

    cloudflare = next(row for row in results if row["seat"] == "cloudflare_workers_ai")
    assert cloudflare["failure_stage"] == "PROVIDER_CALL"
    assert cloudflare["orchestration_error_type"] == "RuntimeError"
    assert cloudflare["dispatch_accepted"] is True
    assert cloudflare["execution_started"] is False
    assert cloudflare["attempted_models"] == []
    assert cloudflare["runtime_execution_events"] == []


def test_cloudflare_round_survives_historical_bridge_result_in_shared_context(monkeypatch):
    seats = _seats()
    monkeypatch.setattr(main, "get_seats", lambda: seats)
    monkeypatch.setattr(main, "_render_live_cascade_telemetry", lambda result: None)

    calls = []
    provider_contexts = {}

    def fake_call(
        seat, user_prompt, shared_context, round_no, local_fallback,
        credential, attachments=None, model_candidates=None, deadline=None, request_id="",
    ):
        calls.append(seat.key)
        provider_contexts[seat.key] = shared_context
        model = (model_candidates or ("test-model",))[0]
        return _fake_success(seat, round_no, request_id, model)

    # DeepSeek is intentionally disabled by the current zero-cost provider policy.
    # The historical Bridge text must not prevent the next eligible seat (Cloudflare)
    # from reaching its official provider call before Gemini.
    credentials = {
        "deepseek": None,
        "cloudflare_workers_ai": "TEST_CREDENTIAL",
        "gemini": "TEST_CREDENTIAL",
    }
    candidates = {
        "deepseek": ("deepseek-flash",),
        "cloudflare_workers_ai": ("@cf/zai-org/glm-4.7-flash",),
        "gemini": ("gemini-test-model",),
    }
    chat = {
        "messages": [
            {
                "role": "user",
                "content": (
                    "Previous final Bridge closure: TRANSACTIONAL BRIDGE — "
                    "BRIDGE_RESULT must remain application-owned."
                ),
            }
        ]
    }

    results = main._run_round(
        "CF_ROUND_OK",
        chat,
        12,
        credentials,
        [],
        candidates,
        "message-test-12",
        None,
        "request-test-12",
    )

    assert calls == ["cloudflare_workers_ai", "gemini"]
    cloudflare = next(row for row in results if row["seat"] == "cloudflare_workers_ai")
    assert cloudflare["status"] == "SUCCESS"
    assert cloudflare["executed_model"] == "@cf/zai-org/glm-4.7-flash"
    assert cloudflare["attempted_models"] == ["@cf/zai-org/glm-4.7-flash"]
    assert "BRIDGE_RESULT" not in provider_contexts["cloudflare_workers_ai"]
    assert "[REDACTED_BRIDGE_KEY]" in provider_contexts["cloudflare_workers_ai"]
    main._assert_provider_boundary(
        "CF_ROUND_OK", provider_contexts["cloudflare_workers_ai"]
    )
