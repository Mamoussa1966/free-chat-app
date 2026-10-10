"""HOTFIX164.11 strict live Bridge and control-plane boundary regression tests.

Provider transport is stubbed, but the tests exercise the real application
orchestrator, bridge transaction writer, evidence store and audit gates.
"""
from __future__ import annotations

import copy
import hashlib
import json

import main
from conversation_persistence_v26 import ensure_persistence_store, persist_identity
from conversation_store import ensure_store
from conversation_v25_runtime import authoritative_audit
from production_platform import build_v23_platform_audit, multi_request_regression_audit, security_audit
from providers import Seat


class SS(dict):
    pass


def _seat(key: str, name: str, slot: int) -> Seat:
    return Seat(key, name, name, (f"{key.upper()}_API_KEY",), (f"{key.upper()}_FREE_MODELS",), "", key, slot)


def _live_result(seat, request_id: str, round_no: int, content: str, user_prompt: str = "", shared_context: str = ""):
    model = "deepseek-flash" if seat.key == "deepseek" else "gemini-3.8-flash"
    payload_json = json.dumps(
        {"contents": [{"parts": [{"text": user_prompt + "\n\n" + shared_context}]}]},
        ensure_ascii=False, sort_keys=True,
    ) if seat.key == "gemini" else ""
    result = {
        "status": "SUCCESS", "classification": "SUCCESS", "seat": seat.key, "name": seat.name,
        "model": model, "executed_model": model, "attempted_models": [model],
        "request_id": request_id, "round": round_no,
        "runtime_execution_events": [{
            "execution_started": True, "status": "SUCCESS", "request_id": request_id,
            "round": round_no, "provider": seat.key, "attempt": 1, "model": model,
        }],
        "attempt_telemetry": [{
            "attempt": 1, "attempt_id": f"{request_id}:r{round_no}:a1",
            "classification": "SUCCESS", "final_result": "SUCCESS", "execution_started": True,
            "model": model, "provider": seat.name, "request_id": request_id, "round": round_no,
            "status_code": 200, "cascade_action": "SUCCESS",
        }],
        "attempt_summaries": [{"attempt": 1, "model": model, "provider": seat.name,
                              "request_id": request_id, "round": round_no, "status": "SUCCESS"}],
        "content": content, "_provider_input_prompt": shared_context,
    }
    if seat.key == "gemini":
        result["_runtime_payload_attestation"] = {
            "payload_json": payload_json,
            "payload_sha256": hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
        }
    return result


def _two_turn_chat(monkeypatch=None):
    chat = {
        "conversation_id": "closure-conversation",
        "session_id": "closure-session",
        "messages": [], "request_ids": [], "request_records": [], "audit_events": [],
        "conversation_record": {"conversation_id": "closure-conversation", "session_id": "closure-session",
                                 "messages": [], "requests": [], "rounds": []},
    }
    ss = SS()
    ensure_persistence_store(ss)
    ensure_store(chat)
    ds, gem = _seat("deepseek", "DeepSeek", 7), _seat("gemini", "Gemini", 2)
    calls = []

    if monkeypatch is not None:
        monkeypatch.setattr(main, "get_seats", lambda: (ds, gem))

        def fake_call(seat, user_prompt, shared_context, round_no, local_fallback, credential,
                      attachments, candidates, deadline, request_id):
            calls.append((request_id, seat.key))
            content = f"LIVE_BRIDGE_VALUE_{round_no}_UNIQUE" if seat.key == "deepseek" else f"Gemini target response {round_no}"
            return _live_result(seat, request_id, round_no, content, user_prompt, shared_context)

        monkeypatch.setattr(main, "call_seat", fake_call)

    for ordinal in (1, 2):
        rid = f"closure-request-{ordinal}-a71f9c0e"
        mid = f"closure-message-{ordinal}-b82e7d1f"
        round_id = f"closure-conversation:{rid}:r{ordinal}"
        request = {
            "request_id": rid, "message_id": mid, "conversation_id": chat["conversation_id"],
            "session_id": chat["session_id"], "canonical_round_base": ordinal,
            "bridge_test_requested": True, "bridge_runtime_contract": "STRICT_LIVE",
            "state": "RUNNING", "results": [], "rounds_executed": 0,
        }
        chat["request_records"].append(request)
        persist_identity(
            chat, ss,
            message={"message_id": mid, "request_id": rid, "conversation_id": chat["conversation_id"],
                     "session_id": chat["session_id"], "role": "user"},
            request=request,
            round_row={"round_id": round_id, "request_id": rid, "message_id": mid,
                       "conversation_id": chat["conversation_id"], "session_id": chat["session_id"],
                       "round": ordinal, "round_number": ordinal, "ordinal": ordinal,
                       "record_type": "CANONICAL_ROUND_RECORD", "canonical_round_record_id": round_id,
                       "canonical_identity_key": round_id,
                       "round_identity_contract": "V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1",
                       "status": "COMPLETED"},
        )
        if monkeypatch is not None:
            prompt = (f"AI Council — FINAL RUNTIME CLOSURE TEST MESSAGE {ordinal} OF 2\n"
                      f"MESSAGE {ordinal} OF 2 — REQUEST {ordinal} / ROUND {ordinal}\n"
                      "TRANSACTIONAL BRIDGE — REQUIRED\nBRIDGE_RESULT must remain application-owned")
            round_results = main._run_round(
                prompt, chat, ordinal,
                {"deepseek": "stub-credential", "gemini": "stub-credential"}, [],
                {"deepseek": ("deepseek-flash",), "gemini": ("gemini-3.8-flash",)},
                mid, None, rid, [],
            )
            request["results"] = copy.deepcopy(round_results)
            request["rounds_executed"] = 1
            request["rounds"] = [ordinal]
            request["state"] = "COMPLETED"
            request["request_metrics"] = main._authoritative_request_metrics(
                rid, round_results, chat.get("audit_events", []),
                chat.get("bridge_runtime_evidence_store", {}), True,
            )
            request["synthesis"] = main.synthesize_council_results(round_results)
            request["synthesis"]["conversation_id"] = chat["conversation_id"]
            request["synthesis"]["session_id"] = chat["session_id"]
            persist_identity(chat, ss, request=request)

    return chat, ss, calls


def _strict_evidence(rid, round_no, bridge_hash, canonical_round_id):
    phases = [
        ("SOURCE_EXECUTION", "SUCCESS"), ("WRITE", "RECORDED"), ("VALIDATE", "PASS"),
        ("COMMIT", "PASS"), ("BARRIER", "PASS"), ("TARGET_DISPATCH", "ACCEPTED"),
        ("TARGET_RESPONSE", "SUCCESS"), ("READ", "PASS"), ("MATCH", "PASS"),
    ]
    return {
        "schema": "bridge-runtime-evidence/v2", "request_id": rid, "round_id": round_no,
        "canonical_round_id": canonical_round_id, "bridge_id_hash": bridge_hash,
        "source_execution_proven": "PASS", "bridge_state_contains_value": "YES",
        "write_status": "PASS", "validate_status": "PASS", "commit_status": "PASS",
        "barrier_status": "PASS", "target_dispatch_status": "PASS", "target_response_status": "PASS",
        "read_status": "PASS", "schema_validation_status": "PASS", "match_status": "PASS",
        "user_prompt_contains_value": "NO", "gemini_input_prompt_contains_value": "NO",
        "user_prompt_contains_bridge_id": "NO", "provider_prompt_contains_bridge_id": "NO",
        "gemini_input_prompt_contains_bridge_id": "NO", "bridge_id_in_gemini_input_prompt": "NO",
        "bridge_id_in_provider_prompt": "NO", "bridge_id_in_user_prompt": "NO",
        "gemini_input_prompt_contains_bridge_key": "NO", "gemini_input_prompt_contains_request_id": "NO",
        "gemini_input_prompt_contains_canonical_round_id": "NO",
        "runtime_http_payload_contains_bridge_id": "NO", "runtime_http_payload_contains_request_id": "NO",
        "runtime_http_payload_contains_canonical_round_id": "NO", "control_plane_identity_leak": "NO",
        "runtime_http_payload_attested": "YES", "runtime_http_payload_contains_value": "NO",
        "runtime_http_payload_contains_bridge_key": "NO", "gemini_received_sanitized_representation_only": "PASS",
        "terminal_state": "COMMITTED", "bridge_state_terminal": "COMMITTED",
        "runtime_sequence_valid": "PASS", "application_owned": "PASS", "bridge_gate_status": "PASS",
        "bridge_trace_count": 2,
        "runtime_sequence": [
            {"seq": i, "phase": phase, "request_id": rid, "round_id": round_no, "status": status}
            for i, (phase, status) in enumerate(phases, 1)
        ],
    }


def test_hotfix164_two_message_real_orchestrator_bridge_closes_fail_closed(monkeypatch):
    chat, ss, calls = _two_turn_chat(monkeypatch)
    assert calls == [("closure-request-1-a71f9c0e", "deepseek"), ("closure-request-1-a71f9c0e", "gemini"),
                     ("closure-request-2-a71f9c0e", "deepseek"), ("closure-request-2-a71f9c0e", "gemini")]
    audit = authoritative_audit(chat, ss)
    assert audit["bridge_runtime_proof_required_message_1"] is True
    assert audit["bridge_runtime_proof_required_message_2"] is True
    assert audit["bridge_runtime_proof_status_message_1"] == "PASS"
    assert audit["bridge_runtime_proof_status_message_2"] == "PASS"
    assert audit["bridge_ids_distinct_message_1_vs_message_2"] is True
    assert audit["bridge_history_proven"] is True

    # Removing either request's app-owned runtime proof must fail closed.
    del chat["bridge_runtime_evidence_store"]["closure-request-1-a71f9c0e"]
    failed = authoritative_audit(chat, ss)
    assert failed["bridge_runtime_proof_required_message_1"] is True
    assert failed["bridge_runtime_proof_status_message_1"] == "NOT_PROVEN"
    assert failed["bridge_history_proven"] is False


def test_hotfix164_platform_audit_requires_real_runtime_proof_for_orchestrated_bridge(monkeypatch):
    chat, ss, _ = _two_turn_chat(monkeypatch)
    sec = security_audit([chat])
    regression = multi_request_regression_audit(chat)
    report = build_v23_platform_audit(
        chat, "closure-request-2-a71f9c0e", {"chars": 1, "digest": "closure-context"},
        [{"status": "READY"}], sec, regression,
    )
    assert regression["gate"] == "PASS"
    assert report["bridge_isolation"]["status"] == "PASS"
    assert report["bridge_isolation"]["bridge_runtime_proof_required"] is True
    assert report["status"] == "PASS"

    # Canonical request identity remains authoritative when a display projection is narrow.
    chat["request_records"] = [r for r in chat["request_records"] if r["request_id"] != "closure-request-2-a71f9c0e"]
    report_narrow = build_v23_platform_audit(
        chat, "closure-request-2-a71f9c0e", {"chars": 1, "digest": "closure-context"},
        [{"status": "READY"}], security_audit([chat]), multi_request_regression_audit(chat),
    )
    assert report_narrow["bridge_isolation"]["status"] == "PASS"
    assert report_narrow["status"] == "PASS"


def test_hotfix164_bridge_security_gate_fails_closed_on_control_plane_identity_leak():
    rid = "closure-request-control-plane-123456"
    source, target = _seat("deepseek", "DeepSeek", 7), _seat("gemini", "Gemini", 2)
    bridge = main.SharedContextBridge(request_id=rid, round_no=1, strict_live_source=True)
    bridge._runtime_bridge_evidence["canonical_round_id"] = f"closure-conversation:{rid}:r1"
    source_result = _live_result(source, rid, 1, "LIVE_BRIDGE_VALUE_CONTROL_PLANE_TEST")
    assert bridge.write_live_source_result(source, source_result) is True
    bridge.commit(target)
    bridge.barrier()
    bridge._record_bridge_event("TARGET_DISPATCH", seat=2, provider="Gemini", status="ACCEPTED")
    # Intentionally inject the Bridge ID into Gemini's recorded input. This is a
    # negative security test: the gate must expose the alias and reject the audit.
    bridge.record_provider_input(target, f"leaked control plane identity {bridge.bridge_id}")
    payload = json.dumps({"contents": [{"parts": [{"text": "clean payload"}]}]}, sort_keys=True)
    bridge.record_runtime_payload_attestation(target, {"payload_json": payload, "payload_sha256": hashlib.sha256(payload.encode()).hexdigest()})
    bridge._record_bridge_event("TARGET_RESPONSE", seat=2, provider="Gemini", status="SUCCESS")
    value = bridge.read("BRIDGE_RESULT", target)
    bridge._record_bridge_event("MATCH", seat=2, provider="Application", status="PASS" if value else "FAIL")
    audit = bridge.seal_runtime_audit(user_prompt="closure test prompt")
    gate = bridge.bridge_security_regression_gate(audit)
    assert audit["BRIDGE_ID_IN_GEMINI_INPUT_PROMPT"] == "YES"
    assert audit["CONTROL_PLANE_IDENTITY_LEAK"] == "YES"
    assert gate["status"] == "FAIL"
    assert "BRIDGE_ID_IN_GEMINI_INPUT_PROMPT" in gate["failures"]


def test_hotfix164_gemini_bridge_prompt_has_no_control_plane_identity():
    rid = "closure-request-prompt-123456"
    bridge = main.SharedContextBridge(request_id=rid, round_no=2, application_owned_test=True)
    canonical_round_id = f"closure-conversation:{rid}:r2"
    bridge._runtime_bridge_evidence["canonical_round_id"] = canonical_round_id
    bridge.seed_application_state("BRIDGE_RESULT", "SECRET_BRIDGE_VALUE_16411", source="DeepSeek", source_seat=7)
    bridge._entries.append(f"request={rid}; round={canonical_round_id}; bridge={bridge.bridge_id}; key=BRIDGE_RESULT")
    prompt = bridge.prompt_snapshot(_seat("gemini", "Gemini", 2))
    assert bridge.bridge_id not in prompt
    assert rid not in prompt
    assert canonical_round_id not in prompt
    assert "BRIDGE_RESULT" not in prompt
    assert "SECRET_BRIDGE_VALUE_16411" not in prompt
