from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

import importlib.util

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("hotfix16429_gate", ROOT / "HOTFIX164.29_INDEPENDENT_CLOSURE_GATE.py")
GATE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(GATE)
CORE = "V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE"
RELEASE = "HOTFIX164.29 — INDEPENDENT HTTP-ATTESTED BRIDGE CLOSURE GATE"
PHASES = GATE.EXPECTED_PHASES
STATUSES = GATE.EXPECTED_EVENT_STATUSES


def _attestation(rid: str, round_id: str, ordinal: int, bridge_hash: str, payload_hash: str):
    return {
        "schema": GATE.EXPECTED_ATTESTATION_SCHEMA,
        "request_id": rid,
        "canonical_round_id": round_id,
        "canonical_round_ordinal": str(ordinal),
        "bridge_id_hash": bridge_hash,
        "source_provider": "DeepSeek", "source_seat": "7",
        "target_provider": "Gemini", "target_seat": "2",
        "executed_model": "configured-free-gemini-model",
        "payload_sha256": payload_hash, "endpoint_sha256": "e" * 64, "payload_bytes": 345,
        "payload_hash_integrity": "PASS", "http_payload_attested": "YES",
        "transport_boundary": GATE.EXPECTED_BOUNDARY, "prepared_request_verified": "YES",
        "request_binding_status": "PASS", "round_binding_status": "PASS",
        "target_binding_status": "PASS", "response_binding_status": "PASS",
        "canonical_round_binding_status": "PASS", "runtime_sequence_valid": "PASS",
        "source_execution_proven": "PASS", "write_status": "PASS", "validate_status": "PASS",
        "commit_status": "PASS", "barrier_status": "PASS", "target_dispatch_status": "PASS",
        "target_response_status": "PASS", "read_status": "PASS", "match_status": "PASS",
        "user_prompt_contains_value": "NO", "target_prompt_contains_value": "NO",
        "http_payload_contains_value": "NO", "http_payload_contains_bridge_key": "NO",
        "http_payload_contains_bridge_id": "NO", "http_payload_contains_request_id": "NO",
        "http_payload_contains_canonical_round_id": "NO", "user_prompt_contains_bridge_id": "NO",
        "provider_prompt_contains_bridge_id": "NO", "target_prompt_contains_bridge_id": "NO",
        "target_prompt_contains_bridge_key": "NO", "target_prompt_contains_request_id": "NO",
        "target_prompt_contains_canonical_round_id": "NO", "control_plane_identity_leak": "NO",
        "sanitized_representation_only": "PASS", "application_owned": "PASS",
        "bridge_gate_status": "PASS", "terminal_state": "COMMITTED", "bridge_state_terminal": "COMMITTED",
        "phase_sequence": [
            {"seq": i + 1, "phase": phase, "status": STATUSES[i],
             "seat": "7" if phase in {"SOURCE_EXECUTION", "WRITE", "VALIDATE"} else "2",
             "target_seat": "2", "request_identity_status": "PASS",
             "round_identity_status": "PASS", "role_identity_status": "PASS"}
            for i, phase in enumerate(PHASES)
        ],
        "expected_phase_sequence": PHASES,
        "raw_payload_exported": False, "raw_prompt_exported": False,
        "raw_bridge_value_exported": False, "raw_bridge_id_exported": False,
    }


def _fixture(tmp_path: Path):
    ids = ["a" * 32, "b" * 32]
    round_ids = [f"conversation:{ids[0]}:r1", f"conversation:{ids[1]}:r2"]
    bridge_hashes = ["1" * 64, "2" * 64]
    rows, requests, proof_rows = [], [], []
    for slot, rid in enumerate(ids, 1):
        rows.append({
            "target_slot": slot, "request_id": rid, "status": "PASS",
            "canonical_request_status": "PASS", "message_request_binding_status": "PASS",
            "canonical_round_binding_status": "PASS", "canonical_round_id": round_ids[slot - 1],
            "canonical_round_ordinal": str(slot), "required_request_artifacts_status": "PASS",
            "bridge_runtime_evidence_record_count_for_request": 1,
            "bridge_projection_record_count_for_request": 1,
            "bridge_projection_binding_status": "PASS", "bridge_request_round_binding_status": "PASS",
            "bridge_proof_status": "PASS", "bridge_id_hash": bridge_hashes[slot - 1],
            "missing_evidence": [], "failure_reasons": [],
            "runtime_http_attestation": _attestation(rid, round_ids[slot - 1], slot, bridge_hashes[slot - 1], str(slot) * 64),
        })
        requests.append({
            "request_id": rid, "status": "PASS", "request_execution_status": "PASS",
            "execution_identity_status": "PASS", "canonical_round_binding_status": "PASS",
            "strict_live_bridge_status": "PASS", "missing_required_artifacts": [],
            "execution_started_count": 2, "actual_model_attestation_present": True,
            "required_artifacts": {k: "PASS" for k in (
                "SESSION_ID", "USER_MESSAGE", "REQUEST_ID", "ROUND_ID", "SEAT_RESULTS",
                "EXECUTED_MODELS", "CASCADE_SUMMARIES", "BRIDGE_AUDIT", "FINAL_RESULT", "AUTHORITATIVE_METRICS")},
        })
        proof_rows.append({"request_id": rid, "status": "PASS", "request_identity_status": "PASS",
                           "canonical_round_binding_status": "PASS", "evidence_record_present": True,
                           "missing_evidence": [], "failure_reasons": []})
    evidence = {
        "schema": GATE.EXPECTED_REPORT_SCHEMA, "status": "PASS", "mode": "READ_ONLY_EXPLICIT_TARGETS",
        "read_only": True, "application_release_identity": RELEASE, "provider_core_identity": CORE,
        "report_generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "security_audit_status": "PASS", "canonical_counter_consistent": True,
        "canonical_identity_chain_valid": True, "canonical_history_hash_stable_during_audit": True,
        "live_state_unchanged": True, "read_side_effects": "NONE_OBSERVED", "read_only_side_effects": "NONE_OBSERVED",
        "provider_execution": 0, "cascade_execution": 0, "new_requests": 0, "new_rounds": 0, "new_bridges": 0,
        "canonical_counts": {"canonical_message_count": 2, "canonical_request_count": 2, "canonical_round_count": 2},
        "audit_active_chat_binding_sha256": "f" * 64, "blockers": [],
        "target_request_count": 2, "target_request_ids": ids, "target_selection_status": "EXPLICIT_TARGETS_SELECTED",
        "target_requests": rows, "requests": requests, "target_bridge_independence_status": "PASS",
        "canonical_request_ids_count": 2, "persisted_request_record_count": 2, "request_diagnostic_count": 2,
        "execution_started_count": 4,
        "strict_live_bridge_proof": {"status": "PASS", "request_count": 2,
            "raw_bridge_id_exported": False, "raw_bridge_value_exported": False,
            "raw_prompt_or_http_body_exported": False, "records": proof_rows},
    }
    manifest = {
        "release": "HOTFIX164.29", "provider_core_identity": CORE,
        "bridge_closure_contract": {"live_final_closure_proven": False},
        "guardrails": {"version_txt_contract_preserved": True},
    }
    evidence_path = tmp_path / "evidence.json"
    manifest_path = tmp_path / "HOTFIX164.29_RELEASE_MANIFEST.json"
    archive_path = tmp_path / "candidate.zip"
    evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    provider_source = f'CURRENT_HOTFIX_RELEASE_VERSION = "{RELEASE}"\n'
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("VERSION.txt", CORE + "\n")
        zf.writestr("providers.py", provider_source)
        zf.writestr("main.py", "def _hotfix16429_export_runtime_http_attestation(): pass\n")
        zf.writestr("HOTFIX164.29_RELEASE_MANIFEST.json", manifest_path.read_bytes())
        zf.writestr("HOTFIX164.29_INDEPENDENT_CLOSURE_GATE.py", "# checker\n")
        zf.writestr(".github/workflows/hotfix164-29-independent-closure.yml", "name: gate\n")
    checksum = tmp_path / "candidate.zip.sha256"
    checksum.write_text(f"{hashlib.sha256(archive_path.read_bytes()).hexdigest()}  {archive_path.name}\n", encoding="utf-8")
    return evidence_path, manifest_path, archive_path, checksum, evidence


def test_independent_gate_passes_complete_fixture_and_binds_archive(tmp_path):
    evidence, manifest, archive, checksum, _ = _fixture(tmp_path)
    report = GATE.verify(evidence, manifest, archive, checksum)
    assert report["status"] == "PASS"
    assert report["live_final_closure_proven"] is True
    assert report["provider_api_calls_made_by_gate"] == 0
    verified_path = tmp_path / "verified.json"
    assert GATE.write_verified_manifest(manifest, verified_path, report) is True
    verified = json.loads(verified_path.read_text(encoding="utf-8"))
    assert verified["bridge_closure_contract"]["live_final_closure_proven"] is True
    assert verified["verified_closure_attestation"]["candidate_archive_sha256"] == report["release_archive_sha256"]


def test_independent_gate_rejects_old_report_without_http_attestation(tmp_path):
    evidence, manifest, archive, checksum, payload = _fixture(tmp_path)
    payload.pop("application_release_identity")
    payload.pop("report_generated_at")
    payload["target_requests"][0].pop("runtime_http_attestation")
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    report = GATE.verify(evidence, manifest, archive, checksum)
    assert report["status"] == "NOT_PROVEN"
    assert "EVIDENCE_APPLICATION_RELEASE_IDENTITY_MISMATCH" in report["errors"]
    assert "EVIDENCE_TIMESTAMP_INVALID_OR_MISSING" in report["errors"]
    assert "TARGET_1_HTTP_ATTESTATION_MISSING" in report["errors"]
    verified_path = tmp_path / "verified.json"
    verified_path.write_text("stale", encoding="utf-8")
    assert GATE.write_verified_manifest(manifest, verified_path, report) is False
    assert not verified_path.exists()


def test_independent_gate_rejects_checksum_mismatch(tmp_path):
    evidence, manifest, archive, checksum, _ = _fixture(tmp_path)
    checksum.write_text("0" * 64 + "  candidate.zip\n", encoding="utf-8")
    report = GATE.verify(evidence, manifest, archive, checksum)
    assert report["status"] == "NOT_PROVEN"
    assert "RELEASE_ARCHIVE_SHA256_SIDECAR_MISMATCH" in report["errors"]


def test_report_http_attestation_export_is_redacted_and_request_bound():
    rid = "request-test"
    evidence = {
        "request_id": rid, "canonical_round_id": "conversation:request-test:r1", "round_id": 1,
        "canonical_round_ordinal": "1", "bridge_id_hash": "a" * 64,
        "source_provider": "DeepSeek", "source_seat": "7", "target_provider": "Gemini", "target_seat": "2",
        "runtime_payload_sha256": "b" * 64, "runtime_payload_endpoint_sha256": "e" * 64, "runtime_payload_bytes": 99,
        "runtime_payload_transport_boundary": GATE.EXPECTED_BOUNDARY,
        "runtime_payload_prepared_request_verified": "YES", "runtime_payload_request_binding_status": "PASS",
        "runtime_payload_round_binding_status": "PASS", "runtime_payload_target_binding_status": "PASS",
        "runtime_payload_response_binding_status": "PASS", "runtime_payload_canonical_round_binding_status": "PASS",
        "runtime_http_payload_hash_integrity": "PASS", "runtime_http_payload_attested": "YES",
        "runtime_sequence_valid": "PASS", "source_execution_proven": "PASS", "write_status": "PASS",
        "validate_status": "PASS", "commit_status": "PASS", "barrier_status": "PASS",
        "target_dispatch_status": "PASS", "target_response_status": "PASS", "read_status": "PASS", "match_status": "PASS",
        "runtime_sequence": [{"seq": i + 1, "phase": phase, "status": status, "seat": "7" if phase in {"SOURCE_EXECUTION", "WRITE", "VALIDATE"} else "2", "target_seat": "2", "request_id": rid, "round_id": 1} for i, (phase, status) in enumerate(zip(PHASES, STATUSES))],
        "user_prompt_contains_value": "NO", "gemini_input_prompt_contains_value": "NO",
        "runtime_http_payload_contains_value": "NO", "runtime_http_payload_contains_bridge_key": "NO",
        "runtime_http_payload_contains_bridge_id": "NO", "runtime_http_payload_contains_request_id": "NO",
        "runtime_http_payload_contains_canonical_round_id": "NO", "user_prompt_contains_bridge_id": "NO",
        "provider_prompt_contains_bridge_id": "NO", "gemini_input_prompt_contains_bridge_id": "NO",
        "gemini_input_prompt_contains_bridge_key": "NO", "gemini_input_prompt_contains_request_id": "NO",
        "gemini_input_prompt_contains_canonical_round_id": "NO", "control_plane_identity_leak": "NO",
        "gemini_received_sanitized_representation_only": "PASS", "application_owned": "PASS",
        "bridge_gate_status": "PASS", "terminal_state": "COMMITTED", "bridge_state_terminal": "COMMITTED",
    }
    report = __import__("main")._hotfix16429_export_runtime_http_attestation(evidence, rid, "1")
    assert report["payload_sha256"] == "b" * 64
    assert report["endpoint_sha256"] == "e" * 64
    assert report["payload_bytes"] == 99
    assert report["phase_sequence"][-1]["request_identity_status"] == "PASS"
    assert report["raw_payload_exported"] is False
    assert "payload_json" not in report

