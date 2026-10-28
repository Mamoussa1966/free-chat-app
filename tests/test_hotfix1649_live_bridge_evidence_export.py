import json
import hashlib

import main
from conversation_store import authoritative_snapshot
from production_platform import multi_request_regression_audit, security_audit
from providers import Seat


def _seat(key, name, slot):
    return Seat(key, name, name, (f"{key.upper()}_API_KEY",), (f"{key.upper()}_FREE_MODELS",), "", key, slot)


def _live_result(seat, request_id, round_no, content):
    model = "deepseek-flash" if seat.key == "deepseek" else "gemini-3.8-flash"
    payload = json.dumps({"input": "sanitized runtime prompt"}, sort_keys=True)
    return {
        "status": "SUCCESS", "classification": "SUCCESS", "seat": seat.key, "name": seat.name,
        "model": model, "executed_model": model, "attempted_models": [model],
        "request_id": request_id, "round": round_no,
        "runtime_execution_events": [{"execution_started": True, "status": "SUCCESS",
                                      "request_id": request_id, "round": round_no, "provider": seat.key}],
        "content": content, "_provider_input_prompt": "sanitized runtime prompt",
        "_runtime_payload_attestation": ({"payload_json": payload,
            "payload_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            "transport_boundary": "requests.PreparedRequest.body", "prepared_request_verified": True,
            "request_id": request_id, "round_no": round_no, "seat_key": "gemini", "seat_slot": 2,
            "executed_model": model, "transport_response_attached": True}
                                         if seat.key == "gemini" else {}),
    }


def _strict_bridge_evidence(rid, round_no, bridge_hash):
    return {
        "request_id": rid, "round_id": round_no, "canonical_round_id": f"c:{rid}:r{round_no}",
        "bridge_id_hash": bridge_hash,
        "source_execution_proven": "PASS", "bridge_state_contains_value": "YES",
        "write_status": "PASS", "validate_status": "PASS", "commit_status": "PASS",
        "barrier_status": "PASS", "target_dispatch_status": "PASS", "target_response_status": "PASS",
        "read_status": "PASS", "schema_validation_status": "PASS", "match_status": "PASS",
        "user_prompt_contains_value": "NO", "gemini_input_prompt_contains_value": "NO",
        "runtime_http_payload_attested": "YES", "runtime_http_payload_contains_value": "NO",
        "runtime_http_payload_contains_bridge_key": "NO", "gemini_received_sanitized_representation_only": "PASS",
        "runtime_http_payload_hash_integrity": "PASS", "runtime_payload_sha256": "a" * 64,
        "runtime_payload_transport_boundary": "requests.PreparedRequest.body",
        "runtime_payload_prepared_request_verified": "YES",
        "runtime_payload_request_binding_status": "PASS", "runtime_payload_round_binding_status": "PASS",
        "runtime_payload_target_binding_status": "PASS", "runtime_payload_response_binding_status": "PASS",
        "runtime_payload_canonical_round_binding_status": "PASS",
        "runtime_sequence_target_identity_status": "PASS",
        "source_provider": "DeepSeek", "source_seat": 7, "target_provider": "Gemini", "target_seat": 2,
        "commit_target_seat": 2, "barrier_target_seat": 2, "read_target_seat": 2,
        "user_prompt_contains_bridge_id": "NO", "provider_prompt_contains_bridge_id": "NO",
        "gemini_input_prompt_contains_bridge_id": "NO",
        "bridge_id_in_gemini_input_prompt": "NO",
        "bridge_id_in_provider_prompt": "NO",
        "bridge_id_in_user_prompt": "NO", "gemini_input_prompt_contains_bridge_key": "NO",
        "gemini_input_prompt_contains_request_id": "NO", "gemini_input_prompt_contains_canonical_round_id": "NO",
        "runtime_http_payload_contains_bridge_id": "NO", "runtime_http_payload_contains_request_id": "NO",
        "runtime_http_payload_contains_canonical_round_id": "NO", "control_plane_identity_leak": "NO",
        "terminal_state": "COMMITTED", "bridge_state_terminal": "COMMITTED",
        "runtime_sequence_valid": "PASS", "application_owned": "PASS",
        "bridge_gate_status": "PASS",
        "runtime_sequence": [
            {"seq": 1, "phase": "SOURCE_EXECUTION", "request_id": rid, "round_id": round_no, "status": "SUCCESS", "seat": 7, "provider": "DeepSeek"},
            {"seq": 2, "phase": "WRITE", "request_id": rid, "round_id": round_no, "status": "RECORDED", "seat": 7, "provider": "DeepSeek", "write_sequence": 1},
            {"seq": 3, "phase": "VALIDATE", "request_id": rid, "round_id": round_no, "status": "PASS", "seat": 7, "provider": "DeepSeek", "write_sequence": 1},
            {"seq": 4, "phase": "COMMIT", "request_id": rid, "round_id": round_no, "status": "PASS", "target_seat": 2},
            {"seq": 5, "phase": "BARRIER", "request_id": rid, "round_id": round_no, "status": "PASS", "seat": 2, "target_seat": 2, "provider": "Gemini"},
            {"seq": 6, "phase": "TARGET_DISPATCH", "request_id": rid, "round_id": round_no, "status": "ACCEPTED", "seat": 2, "target_seat": 2, "provider": "Gemini"},
            {"seq": 7, "phase": "TARGET_RESPONSE", "request_id": rid, "round_id": round_no, "status": "SUCCESS", "seat": 2, "target_seat": 2, "provider": "Gemini"},
            {"seq": 8, "phase": "READ", "request_id": rid, "round_id": round_no, "status": "PASS", "seat": 2, "target_seat": 2, "provider": "Gemini", "read_sequence": 1},
            {"seq": 9, "phase": "MATCH", "request_id": rid, "round_id": round_no, "status": "PASS", "seat": 2, "target_seat": 2, "provider": "Application"},
        ],
    }


def test_hotfix1649_exact_live_prompt_activates_strict_mode():
    prompt = "AI COUNCIL — FINAL RUNTIME CLOSURE TEST MESSAGE 1 OF 2\nTRANSACTIONAL BRIDGE — REQUIRED"
    assert main._is_bridge_test_prompt(prompt, []) is True
    assert main._is_strict_live_bridge_prompt(prompt, []) is True


def test_hotfix1649_live_runtime_metrics_ignore_result_audit_and_use_store_hash():
    rid = "r-live"
    results = [{"seat": "gemini", "request_id": rid, "bridge_transaction_audit": {"BRIDGE_ID": "FAKE_FROM_RESULT"}}]
    store = {rid: {"request_id": rid, "bridge_id_hash": "sha256-bridge-hash"}}
    metrics = main._authoritative_request_metrics(rid, results, [], store, True)
    assert metrics["bridge_ids_source"] == "APPLICATION_OWNED_BRIDGE_RUNTIME_EVIDENCE_STORE"
    assert metrics["bridge_ids"] == ["sha256-bridge-hash"]
    assert metrics["unique_bridge_ids"] == 1
    assert "FAKE_FROM_RESULT" not in metrics["bridge_ids"]
    missing = main._authoritative_request_metrics(rid, results, [], {}, True)
    assert missing["unique_bridge_ids"] == 0
    assert missing["bridge_identity_status"] == "NOT_PROVEN"


def test_hotfix1649_strict_live_bridge_records_only_one_source_write(monkeypatch):
    ds, gem = _seat("deepseek", "DeepSeek", 7), _seat("gemini", "Gemini", 2)
    calls = []

    def fake_call(seat, user_prompt, shared_context, round_no, local_fallback, credential, attachments, candidates, deadline, request_id):
        calls.append(seat.key)
        content = "BRIDGE_WRITE: BRIDGE_RESULT = UNIQUE_CANARY_1649" if seat.key == "deepseek" else "Gemini target response"
        return _live_result(seat, request_id, round_no, content)

    monkeypatch.setattr(main, "get_seats", lambda: (ds, gem))
    monkeypatch.setattr(main, "call_seat", fake_call)
    chat = {"conversation_id": "c", "session_id": "s", "messages": [],
            "conversation_record": {"messages": [], "requests": [], "rounds": [
                {"round_id": "c:r1:r1", "request_id": "r1", "round_number": 1, "ordinal": 1}
            ]}}
    results = main._run_round(
        "AI Council — FINAL RUNTIME CLOSURE TEST MESSAGE 1 OF 2\nTRANSACTIONAL BRIDGE — REQUIRED",
        chat, 1, {"deepseek": "key", "gemini": "key"}, [],
        {"deepseek": ("deepseek-flash",), "gemini": ("gemini-3.8-flash",)},
        "m1", None, "r1", [],
    )
    assert calls == ["deepseek", "gemini"]
    evidence = chat["bridge_runtime_evidence_store"]["r1"]
    assert evidence["request_id"] == "r1"
    assert evidence["canonical_round_id"] == "c:r1:r1"
    assert evidence["write_status"] == "PASS"
    assert evidence["runtime_sequence_valid"] == "PASS"
    assert [e["phase"] for e in evidence["runtime_sequence"]] == [
        "SOURCE_EXECUTION", "WRITE", "VALIDATE", "COMMIT", "BARRIER",
        "TARGET_DISPATCH", "TARGET_RESPONSE", "READ", "MATCH",
    ]
    # The per-result trace is a snapshot and is copied onto more than one result;
    # the authoritative Bridge-owned trace must contain just one write and one read.
    assert evidence["bridge_trace_count"] == 2
    assert [e["phase"] for e in evidence["runtime_sequence"]].count("WRITE") == 1
    assert [e["phase"] for e in evidence["runtime_sequence"]].count("READ") == 1
    assert all("bridge_transaction_audit" not in result for result in results)
    # Materialize the already-created runtime proof on its canonical Request
    # before auditing, matching the production Message -> Request -> Round lifecycle.
    # This test fixture does not synthesize runtime evidence: it copies the actual
    # sanitized record emitted by _run_round.
    evidence["schema"] = str(evidence.get("schema") or "bridge-runtime-evidence/v3")
    evidence["canonical_round_ordinal"] = str(evidence.get("canonical_round_ordinal") or "1")
    chat["conversation_record"]["messages"] = [{
        "message_id": "m1", "request_id": "r1", "conversation_id": "c", "role": "user",
    }]
    chat["conversation_record"]["rounds"][0]["message_id"] = "m1"
    chat["conversation_record"]["requests"] = [{
        "request_id": "r1", "message_id": "m1", "bridge_test_requested": True,
        "bridge_runtime_contract": "STRICT_LIVE", "bridge_runtime_evidence": deepcopy(evidence),
    }]
    # The security gate must consume the application-owned canonical ledger,
    # not provider-result-side audit copies or an unbound cache alone.
    chat["request_records"] = [{
        "request_id": "r1", "bridge_test_requested": True,
        "bridge_runtime_contract": "STRICT_LIVE", "results": results,
    }]
    assert security_audit([chat])["status"] == "PASS"


def test_hotfix1649_export_includes_only_redacted_runtime_bridge_evidence():
    chat = {
        "conversation_id": "c", "session_id": "s",
        "conversation_record": {"messages": [], "requests": [], "rounds": [
            {"round_id": "c:r1:r1", "request_id": "r1", "round_number": 1, "ordinal": 1}
        ]},
        "round_ledger_v24": [],
        "bridge_runtime_evidence_store": {"r1": {
            **_strict_bridge_evidence("r1", 1, "sha256-safe-hash"),
            "bridge_id": "RAW_BRIDGE_ID_SHOULD_NOT_EXPORT",
            "bridge_secret": "RAW_BRIDGE_VALUE_SHOULD_NOT_EXPORT",
            "payload_json": "RAW_HTTP_PAYLOAD_SHOULD_NOT_EXPORT",
            "runtime_sequence": [{"seq": 1, "phase": "WRITE", "request_id": "r1", "round_id": 1,
                                   "value": "RAW_BRIDGE_VALUE_SHOULD_NOT_EXPORT"}],
        }},
    }
    snapshot = authoritative_snapshot(chat)
    exported = snapshot["bridge_runtime_evidence_store"]["r1"]
    serialized = json.dumps(snapshot, sort_keys=True)
    assert exported["bridge_id"] == "[REDACTED]"
    assert exported["bridge_id_hash"] == "sha256-safe-hash"
    assert exported["runtime_sequence"] == [{"seq": 1, "phase": "WRITE", "request_id": "r1", "round_id": 1}]
    assert "RAW_BRIDGE_ID_SHOULD_NOT_EXPORT" not in serialized
    assert "RAW_BRIDGE_VALUE_SHOULD_NOT_EXPORT" not in serialized
    assert "RAW_HTTP_PAYLOAD_SHOULD_NOT_EXPORT" not in serialized
    assert snapshot["rounds"][0]["round_id"] == "c:r1:r1"
    # HOTFIX164.16: sanitized prompt/HTTP boundary assertions must survive export.
    for field in (
        "user_prompt_contains_bridge_id", "provider_prompt_contains_bridge_id",
        "gemini_input_prompt_contains_bridge_id", "bridge_id_in_gemini_input_prompt",
        "bridge_id_in_provider_prompt", "bridge_id_in_user_prompt",
        "gemini_input_prompt_contains_bridge_key", "gemini_input_prompt_contains_request_id",
        "gemini_input_prompt_contains_canonical_round_id",
        "runtime_http_payload_contains_bridge_id", "runtime_http_payload_contains_request_id",
        "runtime_http_payload_contains_canonical_round_id", "control_plane_identity_leak",
    ):
        assert exported[field] == "NO", field
    assert exported["runtime_http_payload_attested"] == "YES"
    assert exported["runtime_http_payload_contains_value"] == "NO"
    assert exported["runtime_http_payload_contains_bridge_key"] == "NO"


def test_hotfix1649_strict_two_request_bridge_regression_recovers_canonical_record_after_cache_loss():
    evidence_1 = {
        **_strict_bridge_evidence("r1", 1, "1" * 64),
        "schema": "bridge-runtime-evidence/v3", "canonical_round_ordinal": "1",
    }
    evidence_2 = {
        **_strict_bridge_evidence("r2", 2, "2" * 64),
        "schema": "bridge-runtime-evidence/v3", "canonical_round_ordinal": "2",
    }
    chat = {
        "conversation_record": {
            "messages": [], "requests": [
                {"request_id": "r1", "bridge_test_requested": True, "bridge_runtime_contract": "STRICT_LIVE", "bridge_runtime_evidence": deepcopy(evidence_1)},
                {"request_id": "r2", "bridge_test_requested": True, "bridge_runtime_contract": "STRICT_LIVE", "bridge_runtime_evidence": deepcopy(evidence_2)},
            ], "rounds": [
                {"round_id": "c:r1:r1", "request_id": "r1", "round_number": 1, "ordinal": 1},
                {"round_id": "c:r2:r2", "request_id": "r2", "round_number": 2, "ordinal": 2},
            ],
        },
        "bridge_runtime_evidence_store": {"r1": deepcopy(evidence_1), "r2": deepcopy(evidence_2)},
        "request_records": [
            {"request_id": "r1", "bridge_test_requested": True, "bridge_runtime_contract": "STRICT_LIVE", "rounds_executed": 1, "results": []},
            {"request_id": "r2", "bridge_test_requested": True, "bridge_runtime_contract": "STRICT_LIVE", "rounds_executed": 1, "results": []},
        ],
    }
    audit = multi_request_regression_audit(chat)
    assert audit["gate"] == "PASS"
    assert audit["unique_bridge_ids"] == 2
    assert audit["bridge_ids_source"] == "APPLICATION_OWNED_BRIDGE_RUNTIME_EVIDENCE_STORE"
    chat["bridge_runtime_evidence_store"]["r2"].pop("bridge_gate_status")
    assert multi_request_regression_audit(chat)["gate"] == "FAIL"

    # A consistent but empty sidecar is recoverable from the canonical request.
    chat["bridge_runtime_evidence_store"]["r2"] = deepcopy(evidence_2)
    del chat["bridge_runtime_evidence_store"]["r2"]
    recovered = multi_request_regression_audit(chat)
    assert recovered["gate"] == "PASS"
    assert recovered["strict_bridge_proof_missing"] is False

    # Missing canonical proof remains a hard failure.
    chat["conversation_record"]["requests"][1].pop("bridge_runtime_evidence")
    failed = multi_request_regression_audit(chat)
    assert failed["gate"] == "FAIL"
    assert failed["strict_bridge_proof_missing"] is True
    assert failed["checks"]["BRIDGE_ID_REQUEST_ISOLATION"] is False



def test_hotfix16416_export_does_not_mask_detected_control_plane_leaks():
    evidence = _strict_bridge_evidence("r1", 1, "sha256-safe-hash")
    evidence["provider_prompt_contains_bridge_id"] = "YES"
    evidence["runtime_http_payload_contains_bridge_id"] = "YES"
    evidence["control_plane_identity_leak"] = "YES"
    chat = {
        "conversation_id": "c",
        "session_id": "s",
        "conversation_record": {
            "messages": [], "requests": [],
            "rounds": [{"round_id": "c:r1:r1", "request_id": "r1", "round_number": 1, "ordinal": 1}],
        },
        "round_ledger_v24": [],
        "bridge_runtime_evidence_store": {"r1": evidence},
    }
    exported = authoritative_snapshot(chat)["bridge_runtime_evidence_store"]["r1"]
    assert exported["provider_prompt_contains_bridge_id"] == "YES"
    assert exported["runtime_http_payload_contains_bridge_id"] == "YES"
    assert exported["control_plane_identity_leak"] == "YES"



def test_hotfix16417_exports_two_independent_redacted_bridge_records_from_runtime_store():
    r1 = _strict_bridge_evidence("r1", 1, "1" * 64)
    r2 = _strict_bridge_evidence("r2", 2, "2" * 64)
    chat = {
        "conversation_id": "c", "session_id": "s",
        "conversation_record": {
            "messages": [],
            "requests": [
                {"request_id": "r1", "bridge_test_requested": True, "bridge_runtime_contract": "STRICT_LIVE", "bridge_runtime_evidence": r1},
                {"request_id": "r2", "bridge_test_requested": True, "bridge_runtime_contract": "STRICT_LIVE", "bridge_runtime_evidence": r2},
            ],
            "rounds": [
                {"round_id": "c:r1:r1", "request_id": "r1", "round_number": 1, "ordinal": 1},
                {"round_id": "c:r2:r2", "request_id": "r2", "round_number": 2, "ordinal": 2},
            ],
        },
        "round_ledger_v24": [],
        "bridge_runtime_evidence_store": {"r1": r1, "r2": r2},
    }
    snapshot = authoritative_snapshot(chat)
    exported = snapshot["bridge_runtime_evidence_export"]
    assert exported["authoritative_source"] == "APPLICATION_OWNED_RUNTIME_RECORDS_ONLY"
    assert exported["status"] == "PASS"
    assert exported["request_count"] == 2
    assert exported["bridge_id_uniqueness_status"] == "PASS"
    records = {x["request_id"]: x for x in exported["records"]}
    assert set(records) == {"r1", "r2"}
    assert records["r1"]["export_status"] == records["r2"]["export_status"] == "PASS"
    assert records["r1"]["canonical_round_id"] == "c:r1:r1"
    assert records["r2"]["canonical_round_id"] == "c:r2:r2"
    assert records["r1"]["bridge_id_hash"] != records["r2"]["bridge_id_hash"]
    for record in records.values():
        assert record["bridge_id"] == "[REDACTED]"
        assert [x["phase"] for x in record["runtime_sequence"]] == [
            "SOURCE_EXECUTION", "WRITE", "VALIDATE", "COMMIT", "BARRIER",
            "TARGET_DISPATCH", "TARGET_RESPONSE", "READ", "MATCH",
        ]
        assert record["runtime_sequence_target_identity_status"] == "PASS"
        assert record["runtime_http_payload_attested"] == "YES"
        assert record["runtime_http_payload_hash_integrity"] == "PASS"
        assert record["runtime_payload_prepared_request_verified"] == "YES"
    serialized = json.dumps(exported, sort_keys=True)
    assert "RAW_BRIDGE_ID" not in serialized
    assert "RAW_BRIDGE_VALUE" not in serialized
    assert '"payload_json"' not in serialized


def test_hotfix16417_export_fails_when_commit_did_not_bind_target_seat_two():
    evidence = _strict_bridge_evidence("r1", 1, "1" * 64)
    evidence["runtime_sequence"][3]["target_seat"] = 0
    evidence["commit_target_seat"] = 0
    chat = {
        "conversation_id": "c", "session_id": "s",
        "conversation_record": {
            "messages": [], "requests": [
                {"request_id": "r1", "bridge_test_requested": True, "bridge_runtime_contract": "STRICT_LIVE", "bridge_runtime_evidence": evidence},
            ],
            "rounds": [{"round_id": "c:r1:r1", "request_id": "r1", "round_number": 1, "ordinal": 1}],
        },
        "round_ledger_v24": [],
        "bridge_runtime_evidence_store": {"r1": evidence},
    }
    exported = authoritative_snapshot(chat)["bridge_runtime_evidence_export"]
    assert exported["records"][0]["export_status"] == "FAIL"
    assert exported["records"][0]["target_identity_status"] == "FAIL"
    assert exported["status"] == "FAIL"
