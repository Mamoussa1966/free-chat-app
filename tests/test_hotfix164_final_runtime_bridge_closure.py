import hashlib
import json

import main
from conversation_runtime import ensure_conversation_state
from conversation_store import prepare_historical_runtime
from conversation_v25_runtime import authoritative_audit
from production_platform import build_v23_platform_audit


BRIDGE_PROMPT = "TRANSACTIONAL BRIDGE ISOLATION\nProve application-owned DeepSeek Seat 7 to Gemini Seat 2 Bridge lifecycle and canonical persistence."


def _runtime_result(seat, shared_context, model, request_id, round_no):
    payload = json.dumps({"input": shared_context}, ensure_ascii=False, sort_keys=True)
    event = {
        "execution_started": True,
        "request_id": request_id,
        "round": round_no,
        "attempt": 1,
        "model": model,
        "status": "SUCCESS",
        "classification": "SUCCESS",
    }
    return {
        "seat": seat.key,
        "name": seat.name,
        "label": seat.label,
        "status": "SUCCESS",
        "mode": "official_api",
        "content": "ordinary provider response",
        "request_id": request_id,
        "round": round_no,
        "model": model,
        "executed_model": model,
        "provider_reported_model": model,
        "attempted_models": [model],
        "attempt_diagnostics": [{
            "attempt": 1, "model": model, "status_code": 200,
            "classification": "SUCCESS", "retryable": False,
            "latency": 0.001, "request_id": request_id, "round": round_no,
            "provider": seat.key, "final_result": "SUCCESS",
        }],
        "attempt_summaries": [{"attempt": 1, "model": model, "status": "SUCCESS"}],
        "runtime_execution_events": [event],
        "official_authenticated": True,
        "_provider_input_prompt": shared_context,
        "_runtime_payload_attestation": {
            "payload_json": payload,
            "payload_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        },
    }


def _run_two_real_bridge_requests(monkeypatch):
    ss = {}
    monkeypatch.setattr(main.st, "session_state", ss, raising=False)
    chat = {
        "id": "hotfix164-final-runtime",
        "messages": [],
        "request_records": [],
        "history_identity_ledger": [],
        "result_keys": [],
        "audit_events": [],
    }
    ensure_conversation_state(chat)
    seats = main.get_seats()
    credentials = {seat.key: "TEST" for seat in seats}
    models = {seat.key: (f"{seat.key}-model",) for seat in seats}

    def fake_call(seat, user_prompt, shared_context, round_no, local_fallback,
                  credential, attachments, model_candidates, deadline, request_id):
        return _runtime_result(seat, shared_context, model_candidates[0], request_id, round_no)

    monkeypatch.setattr(main, "call_seat", fake_call)
    monkeypatch.setattr(main, "_provider_identity_matches", lambda *args, **kwargs: True)

    main._run_council(BRIDGE_PROMPT, chat, 1, credentials, [], models, "m1", "req1")

    # Simulate Streamlit's current-request narrowing between user turns.
    committed = chat["conversation_record"]
    chat["conversation_record"] = {
        "conversation_id": committed["conversation_id"],
        "session_id": committed["session_id"],
        "messages": [committed["messages"][-1]],
        "requests": [committed["requests"][-1]],
        "rounds": [committed["rounds"][-1]],
    }
    prepare_historical_runtime(chat, ss)

    main._run_council(BRIDGE_PROMPT, chat, 1, credentials, [], models, "m2", "req2")
    return chat, ss


def test_hotfix164_gemini_bridge_prompt_has_no_control_plane_identity(monkeypatch):
    bridge = main.SharedContextBridge(request_id="req164", round_no=2, application_owned_test=True)
    bridge.seed_application_state("BRIDGE_RESULT", "HOTFIX164-PRIVATE-CANARY", source="DeepSeek", source_seat=7)
    gemini = next(seat for seat in main.get_seats() if seat.key == "gemini")
    prompt = bridge.prompt_snapshot(gemini)
    assert "BRIDGE CONTEXT CAPABILITY (SANITIZED)" in prompt
    assert bridge.bridge_id not in prompt
    assert "bridge_id:" not in prompt
    assert "round_id:" not in prompt
    assert "HOTFIX164-PRIVATE-CANARY" not in prompt
    assert "BRIDGE_RESULT" not in prompt


def test_hotfix164_two_message_real_orchestrator_bridge_closes_fail_closed(monkeypatch):
    chat, ss = _run_two_real_bridge_requests(monkeypatch)
    audit = authoritative_audit(chat, ss)

    assert audit["canonical_message_count"] == 2
    assert audit["canonical_request_count"] == 2
    assert audit["canonical_round_count"] == 2
    assert audit["canonical_round_ordinals"] == [1, 2]
    assert audit["request_1_round_1_mapping"] is True
    assert audit["request_2_round_2_mapping"] is True
    assert audit["request_2_round_1_mapping"] is False
    assert audit["bridge_exactly_one_message_1"] is True
    assert audit["bridge_exactly_one_message_2"] is True
    assert audit["bridge_ids_distinct_message_1_vs_message_2"] is True
    assert audit["bridge_ids_unique_when_present"] is True
    assert audit["bridge_runtime_proof_required_message_1"] is True
    assert audit["bridge_runtime_proof_required_message_2"] is True
    assert audit["bridge_runtime_proof_message_1"] is True
    assert audit["bridge_runtime_proof_message_2"] is True
    assert audit["bridge_history_proven"] is True
    assert audit["conversation_runtime_audit"] == "PASS"
    assert audit["overall_authoritative_status"] == "PASS"

    for key in ("bridge_lifecycle_message_1", "bridge_lifecycle_message_2"):
        row = audit[key]
        assert row["SOURCE"] == "DeepSeek / Seat 7"
        assert row["TARGET"] == "Gemini / Seat 2"
        assert row["bridge_lifecycle_events"] == ["WRITE", "VALIDATE", "COMMIT", "BARRIER", "READ"]
        assert row["bridge_lifecycle_complete"] == "PASS"
        assert row["bridge_count_for_request"] == 1
        assert row["MATCH"] == "PASS"
        assert row["RUNTIME_HTTP_PAYLOAD_ATTESTED"] == "YES"
        assert row["RUNTIME_HTTP_PAYLOAD_CONTAINS_VALUE"] == "NO"
        assert row["RUNTIME_HTTP_PAYLOAD_CONTAINS_BRIDGE_KEY"] == "NO"
        assert row["BRIDGE_ID_IN_USER_PROMPT"] == "NO"
        assert row["BRIDGE_ID_IN_GEMINI_INPUT_PROMPT"] == "NO"
        assert row["BRIDGE_ID_IN_RUNTIME_HTTP_PAYLOAD"] == "NO"
        assert row["ROUND_ID_IN_GEMINI_INPUT_PROMPT"] == "NO"
        assert row["ROUND_ID_IN_RUNTIME_HTTP_PAYLOAD"] == "NO"
        assert row["GEMINI_RECEIVED_SANITIZED_REPRESENTATION_ONLY"] == "PASS"
        assert row["AUDIT_SEALED"] == "YES"
        assert row["PRODUCTION_GATE"] == "PASS"

    # The private bridge value exists only in application-owned control state and
    # is never copied into assistant content/history.
    persisted = chat["request_records"]
    for request in persisted:
        state = request.get("application_owned_bridge_state") or {}
        value = (((state.get("values") or {}).get("BRIDGE_RESULT") or {}).get("value"))
        assert value and value.startswith("HOTFIX124_BRIDGE_RUNTIME_")
        for result in request.get("results") or []:
            assert value not in str(result.get("content") or "")
            assert value not in json.dumps(result, ensure_ascii=False)


def test_hotfix164_platform_audit_requires_real_runtime_proof_for_orchestrated_bridge(monkeypatch):
    chat, ss = _run_two_real_bridge_requests(monkeypatch)
    latest_request = chat["request_records"][-1]["request_id"]
    report = build_v23_platform_audit(
        chat,
        latest_request,
        {"chars": 1, "digest": "context"},
        [{"status": "READY"}] * len(main.get_seats()),
        {"status": "PASS"},
        {"gate": "PASS"},
    )
    assert report["status"] == "PASS"
    assert report["bridge_isolation"]["runtime_proof_required"] is True
    assert report["bridge_isolation"]["status"] == "PASS"


def test_hotfix164_bridge_security_gate_fails_closed_on_control_plane_identity_leak(monkeypatch):
    bridge = main.SharedContextBridge(request_id="req164-leak", round_no=1, application_owned_test=True)
    bridge.seed_application_state("BRIDGE_RESULT", "HOTFIX164-PRIVATE-FAIL-CLOSED", source="DeepSeek", source_seat=7)
    gemini = next(seat for seat in main.get_seats() if seat.key == "gemini")
    bridge.commit(gemini)
    bridge.barrier()
    bridge.read("BRIDGE_RESULT", gemini)
    # Simulate a malicious/incorrect provider-boundary implementation. The new
    # gate must reject it even when the bridge lifecycle itself is complete.
    bridge.record_provider_input(gemini, f"bridge_id: {bridge.bridge_id}")
    bridge.record_runtime_payload_attestation(
        gemini,
        {"payload_json": f"{{\"input\":\"bridge_id: {bridge.bridge_id}\"}}", "payload_sha256": "attested"},
    )
    audit = bridge.transaction_audit(user_prompt="clean")
    assert audit["BRIDGE_ID_IN_GEMINI_INPUT_PROMPT"] == "YES"
    assert audit["BRIDGE_ID_IN_RUNTIME_HTTP_PAYLOAD"] == "YES"
    assert bridge.bridge_security_regression_gate(audit)["status"] == "FAIL"
