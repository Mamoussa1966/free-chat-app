from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import zipfile

from hotfix16430_deployment_attestation import compute_source_bundle

ROOT = Path(__file__).resolve().parents[1]
TARGET_IDS = (
    "025b74c0d0e044ac9a54cb56d4bd85f8",
    "947c8cd69e0c4349892423af4751a426",
)
DEPLOYED_SHA = "a" * 40
CORE = "V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE"
APP_IDENTITY = "HOTFIX164.30 — DEPLOYED-COMMIT-BOUND LIVE CLOSURE"
PHASES = [
    "SOURCE_EXECUTION", "WRITE", "VALIDATE", "COMMIT", "BARRIER",
    "TARGET_DISPATCH", "TARGET_RESPONSE", "READ", "MATCH",
]
PHASE_STATUSES = [
    "SUCCESS", "RECORDED", "PASS", "PASS", "PASS",
    "ACCEPTED", "SUCCESS", "PASS", "PASS",
]


def _load_gate():
    path = ROOT / "HOTFIX164.30_DEPLOYMENT_COMMIT_GATE.py"
    spec = importlib.util.spec_from_file_location("hotfix16430_scoped_target_gate_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _artifact_map(*, incomplete: bool = False, bridge: bool = False) -> dict[str, str]:
    return {
        "SESSION_ID": "PASS",
        "USER_MESSAGE": "PASS",
        "REQUEST_ID": "PASS",
        "ROUND_ID": "PASS",
        "SEAT_RESULTS": "PASS",
        "EXECUTED_MODELS": "NOT_PROVEN" if incomplete else "PASS",
        "CASCADE_SUMMARIES": "NOT_PROVEN" if incomplete else "PASS",
        "BRIDGE_AUDIT": "PASS" if bridge else "NOT_REQUESTED",
        "FINAL_RESULT": "PASS",
        "AUTHORITATIVE_METRICS": "PASS",
    }


def _request_diagnostic(
    rid: str, ordinal: int, started: int, *, incomplete: bool = False, bridge: bool = False
) -> dict:
    return {
        "request_id": rid,
        "canonical_request_present": True,
        "direct_request_projection_present": True,
        "message_identity_status": "PASS",
        "canonical_round_binding_status": "PASS",
        "canonical_round_records_for_request": 1,
        "canonical_round_ordinals": [ordinal],
        "result_request_identity_status": "PASS",
        "request_execution_status": "NOT_PROVEN" if incomplete else "PASS",
        "execution_identity_status": "NOT_PROVEN" if incomplete else "PASS",
        "execution_started_count": started,
        "result_record_count": 6,
        "actual_model_attestation_present": not incomplete,
        "cascade_summary_present": not incomplete,
        "synthesis_record_present": True,
        "authoritative_metrics_present": True,
        "bridge_requested": bridge,
        "bridge_contract": "STRICT_LIVE" if bridge else "NOT_REQUESTED",
        "strict_live_bridge_status": "PASS" if bridge else "NOT_REQUESTED",
        "required_artifacts": _artifact_map(incomplete=incomplete, bridge=bridge),
        "missing_required_artifacts": (
            ["CASCADE_SUMMARIES", "EXECUTED_MODELS"] if incomplete else []
        ),
        "status": "NOT_PROVEN" if incomplete else "PASS",
    }


def _target_request_row(rid: str, ordinal: int) -> dict:
    round_id = f"test-conversation:{rid}:r{ordinal}"
    bridge_hash = hashlib.sha256(f"bridge-{ordinal}".encode()).hexdigest()
    payload_hash = hashlib.sha256(f"prepared-body-{ordinal}".encode()).hexdigest()
    endpoint_hash = hashlib.sha256(b"https://generativelanguage.googleapis.com").hexdigest()
    phases = [
        {
            "seq": index,
            "phase": phase,
            "status": PHASE_STATUSES[index - 1],
            "request_identity_status": "PASS",
            "round_identity_status": "PASS",
            "role_identity_status": "PASS",
        }
        for index, phase in enumerate(PHASES, start=1)
    ]
    attestation = {
        "schema": "hotfix164.29-runtime-http-attestation/v1",
        "request_id": rid,
        "canonical_round_id": round_id,
        "canonical_round_ordinal": str(ordinal),
        "bridge_id_hash": bridge_hash,
        "source_provider": "DeepSeek",
        "source_seat": "7",
        "target_provider": "Gemini",
        "target_seat": "2",
        "executed_model": "gemini-3.6-flash",
        "payload_sha256": payload_hash,
        "endpoint_sha256": endpoint_hash,
        "payload_bytes": 2048 + ordinal,
        "payload_hash_integrity": "PASS",
        "http_payload_attested": "YES",
        "transport_attempt_status": "HTTP_RESPONSE_RECEIVED",
        "transport_http_status_code": 200,
        "transport_error_class": "NOT_PROVEN",
        "transport_boundary": "requests.PreparedRequest.body",
        "prepared_request_verified": "YES",
        "request_binding_status": "PASS",
        "round_binding_status": "PASS",
        "target_binding_status": "PASS",
        "response_binding_status": "PASS",
        "canonical_round_binding_status": "PASS",
        "runtime_sequence_valid": "PASS",
        "source_execution_proven": "PASS",
        "write_status": "PASS",
        "validate_status": "PASS",
        "commit_status": "PASS",
        "barrier_status": "PASS",
        "target_dispatch_status": "PASS",
        "target_response_status": "PASS",
        "read_status": "PASS",
        "match_status": "PASS",
        "user_prompt_contains_value": "NO",
        "target_prompt_contains_value": "NO",
        "http_payload_contains_value": "NO",
        "http_payload_contains_bridge_key": "NO",
        "http_payload_contains_bridge_id": "NO",
        "http_payload_contains_request_id": "NO",
        "http_payload_contains_canonical_round_id": "NO",
        "user_prompt_contains_bridge_id": "NO",
        "provider_prompt_contains_bridge_id": "NO",
        "target_prompt_contains_bridge_id": "NO",
        "target_prompt_contains_bridge_key": "NO",
        "target_prompt_contains_request_id": "NO",
        "target_prompt_contains_canonical_round_id": "NO",
        "control_plane_identity_leak": "NO",
        "sanitized_representation_only": "PASS",
        "application_owned": "PASS",
        "bridge_gate_status": "PASS",
        "terminal_state": "COMMITTED",
        "bridge_state_terminal": "COMMITTED",
        "phase_sequence": phases,
        "expected_phase_sequence": PHASES,
        "raw_payload_exported": False,
        "raw_prompt_exported": False,
        "raw_bridge_value_exported": False,
        "raw_bridge_id_exported": False,
    }
    return {
        "target_slot": ordinal,
        "request_id": rid,
        "canonical_request_status": "PASS",
        "message_request_binding_status": "PASS",
        "canonical_round_binding_status": "PASS",
        "canonical_round_id": round_id,
        "canonical_round_ordinal": str(ordinal),
        "required_request_artifacts_status": "PASS",
        "bridge_runtime_evidence_record_count_for_request": 1,
        "bridge_projection_record_count_for_request": 1,
        "bridge_projection_binding_status": "PASS",
        "bridge_request_round_binding_status": "PASS",
        "bridge_proof_status": "PASS",
        "bridge_id_hash": bridge_hash,
        "runtime_http_attestation": attestation,
        "missing_evidence": [],
        "failure_reasons": [],
        "status": "PASS",
    }


def _valid_inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Build a provider-free 14-row fixture with two explicit, fully attested targets."""
    target_rows = [_target_request_row(rid, slot) for slot, rid in enumerate(TARGET_IDS, start=1)]
    requests = [
        _request_diagnostic(rid, slot, 2, bridge=True)
        for slot, rid in enumerate(TARGET_IDS, start=1)
    ]

    # Ten other historical Requests have complete execution diagnostics.
    pass_counts = [2, 2, 2, 2, 2, 2, 3, 3, 2, 2]
    for ordinal, started in enumerate(pass_counts, start=3):
        requests.append(_request_diagnostic(f"{ordinal:032x}", ordinal, started))
    # These two unselected rows are incomplete, not contradictory: their
    # canonical identity chain is valid, but their execution artifacts are absent.
    for ordinal in (13, 14):
        requests.append(
            _request_diagnostic(f"{ordinal:032x}", ordinal, 0, incomplete=True)
        )

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    canonical_counts = {
        "canonical_message_count": 14,
        "canonical_request_count": 14,
        "canonical_round_count": 14,
    }
    blockers = [
        f"REQUEST_ARTIFACTS_NOT_PROVEN:{13:032x}:CASCADE_SUMMARIES,EXECUTED_MODELS",
        f"REQUEST_ARTIFACTS_NOT_PROVEN:{14:032x}:CASCADE_SUMMARIES,EXECUTED_MODELS",
        f"REQUEST_EXECUTION_NOT_PROVEN:{13:032x}",
        f"REQUEST_EXECUTION_NOT_PROVEN:{14:032x}",
    ]
    evidence = {
        "schema": "hotfix164.23-explicit-target-read-only-forensics/v1",
        "status": "NOT_PROVEN",
        "mode": "READ_ONLY_EXPLICIT_TARGETS",
        "read_only": True,
        "authoritative_source": "V26_3_CANONICAL_CONVERSATION_STORE_AND_APPLICATION_OWNED_BRIDGE_RUNTIME_EVIDENCE",
        "canonical_counts": canonical_counts,
        "canonical_counter_consistent": True,
        "canonical_counter_status": "PASS",
        "canonical_vs_persisted_request_counter_status": "PASS",
        "canonical_identity_chain_valid": True,
        "canonical_history_hash_stable_during_audit": True,
        "request_created_count": 14,
        "request_diagnostic_count": 14,
        "execution_started_count": 26,
        "runtime_execution_event_count": 26,
        "execution_started_source": "PERSISTED_APPLICATION_OWNED_RUNTIME_EXECUTION_EVENTS_ONLY",
        "requests": requests,
        "target_request_count": 2,
        "target_request_ids": list(TARGET_IDS),
        "target_selection_status": "EXPLICIT_TARGETS_SELECTED",
        "target_requests": target_rows,
        "target_bridge_independence_status": "PASS",
        "security_audit_status": "PASS",
        "blockers": blockers,
        "read_side_effects": "NONE_OBSERVED",
        "read_only_side_effects": "NONE_OBSERVED",
        "read_only_live_state_unchanged": True,
        "live_state_unchanged": True,
        "provider_execution": 0,
        "cascade_execution": 0,
        "new_requests": 0,
        "new_rounds": 0,
        "new_bridges": 0,
        "application_release_identity": APP_IDENTITY,
        "provider_core_identity": CORE,
        "report_generated_at": now,
        "historical_records_preserved": True,
        "historical_canonical_counts_unchanged": canonical_counts,
        "persisted_request_record_count": 14,
        "canonical_request_ids_count": 14,
        "canonical_vs_persisted_request_counter_status": "PASS",
        "duplicate_canonical_request_ids": [],
        "projection_only_request_ids": [],
        "canonical_counter_status": "PASS",
        "audit_active_chat_binding_sha256": hashlib.sha256(b"active-chat").hexdigest(),
        "request_diagnostic_count": 14,
        "strict_live_bridge_proof": {
            "schema": "strict-live-bridge-proof-diagnostics/v1",
            "status": "PASS",
            "request_count": 2,
            "records": [
                {
                    "request_id": rid,
                    "status": "PASS",
                    "evidence_record_present": True,
                    "request_identity_status": "PASS",
                    "canonical_round_binding_status": "PASS",
                    "missing_evidence": [],
                    "failure_reasons": [],
                    "conflicting_cache_fields": [],
                }
                for rid in TARGET_IDS
            ],
            "authoritative_source": "APPLICATION_OWNED_BRIDGE_RUNTIME_EVIDENCE_STORE",
            "fail_closed_rule": "MISSING_OR_INCOMPLETE_EVIDENCE_NEVER_PASSES",
            "raw_bridge_id_exported": False,
            "raw_bridge_value_exported": False,
            "raw_prompt_or_http_body_exported": False,
        },
    }

    bundle = compute_source_bundle(ROOT)
    assert bundle["source_bundle_complete"] is True
    evidence["deployment_attestation"] = {
        "schema": "hotfix164.30-deployment-source-attestation/v1",
        "repository": "Mamoussa1966/free-chat-app",
        "expected_deployment_branch": "gitops-v0.4-final",
        "application_release_identity": APP_IDENTITY,
        "provider_core_identity": CORE,
        "generated_at_utc": now,
        "observed_git_commit_sha": DEPLOYED_SHA,
        "observed_git_commit_source": "git_rev_parse_HEAD",
        "source_bundle_sha256": bundle["source_bundle_sha256"],
        "source_file_sha256": bundle["source_file_sha256"],
        "source_bundle_complete": True,
        "missing_source_files": [],
        "commit_binding_status": "SOURCE_BUNDLE_READY",
        "read_only": True,
        "provider_api_calls_made": 0,
        "raw_payload_exported": False,
        "secrets_exported": False,
    }

    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest_path = ROOT / "HOTFIX164.30_RELEASE_MANIFEST.json"
    manifest_copy = tmp_path / "manifest.json"
    manifest_copy.write_bytes(manifest_path.read_bytes())

    archive_path = tmp_path / "candidate.zip"
    archive_members = (
        "VERSION.txt",
        "providers.py",
        "main.py",
        "HOTFIX164.30_RELEASE_MANIFEST.json",
        "HOTFIX164.30_DEPLOYMENT_COMMIT_GATE.py",
        "hotfix16430_deployment_attestation.py",
        ".github/workflows/hotfix164-30-deployment-commit-closure.yml",
    )
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for member in archive_members:
            archive.write(ROOT / member, member)

    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    checksum_path = tmp_path / "candidate.zip.sha256"
    checksum_path.write_text(f"{digest}  {archive_path.name}\n", encoding="utf-8")
    return evidence_path, manifest_copy, archive_path, checksum_path


def _verify(tmp_path: Path):
    evidence, manifest, archive, checksum = _valid_inputs(tmp_path)
    result = _load_gate().verify(evidence, manifest, archive, checksum, DEPLOYED_SHA)
    return result, evidence, manifest, archive, checksum


def test_explicit_targets_pass_while_global_history_remains_14_and_non_target_gaps_are_reported(tmp_path):
    result, *_ = _verify(tmp_path)

    assert result["status"] == "PASS", result["errors"]
    assert result["live_final_closure_proven"] is True
    assert result["targeted_scope_status"] == "PASS"
    assert result["historical_scope_status"] == "PASS"
    assert result["historical_scope"]["canonical_history_count"] == 14
    assert result["historical_scope"]["canonical_message_count"] == 14
    assert result["historical_scope"]["canonical_round_count"] == 14
    assert result["historical_scope"]["execution_started_count"] == 26
    assert result["historical_scope"]["non_target_not_proven_request_ids"] == [
        f"{13:032x}", f"{14:032x}"
    ]
    assert len(result["historical_scope"]["non_target_blockers"]) == 4
    assert result["provider_api_calls_made_by_gate"] == 0
    assert result["gate_is_read_only"] is True


def test_target_request_cannot_be_downgraded_to_non_target_not_proven(tmp_path):
    _, evidence_path, manifest, archive, checksum = _verify(tmp_path)
    report = json.loads(evidence_path.read_text(encoding="utf-8"))
    target_id = report["target_request_ids"][0]
    row = next(item for item in report["requests"] if item["request_id"] == target_id)
    row.update({
        "status": "NOT_PROVEN",
        "request_execution_status": "NOT_PROVEN",
        "execution_identity_status": "NOT_PROVEN",
        "execution_started_count": 0,
        "actual_model_attestation_present": False,
        "cascade_summary_present": False,
        "missing_required_artifacts": ["CASCADE_SUMMARIES", "EXECUTED_MODELS"],
        "required_artifacts": _artifact_map(incomplete=True, bridge=True),
    })
    report["blockers"].extend([
        f"REQUEST_ARTIFACTS_NOT_PROVEN:{target_id}:CASCADE_SUMMARIES,EXECUTED_MODELS",
        f"REQUEST_EXECUTION_NOT_PROVEN:{target_id}",
    ])
    evidence_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")

    blocked = _load_gate().verify(evidence_path, manifest, archive, checksum, DEPLOYED_SHA)
    assert blocked["status"] == "NOT_PROVEN"
    assert blocked["targeted_scope_status"] == "NOT_PROVEN"
    assert any(error.startswith(f"TARGET_DIAGNOSTIC_NOT_PASS:{target_id}") for error in blocked["errors"])


def test_historical_counter_mismatch_still_blocks_target_closure(tmp_path):
    _, evidence_path, manifest, archive, checksum = _verify(tmp_path)
    report = json.loads(evidence_path.read_text(encoding="utf-8"))
    report["canonical_counts"]["canonical_request_count"] = 13
    evidence_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")

    blocked = _load_gate().verify(evidence_path, manifest, archive, checksum, DEPLOYED_SHA)
    assert blocked["status"] == "NOT_PROVEN"
    assert "HISTORY_MESSAGE_REQUEST_ROUND_COUNTS_DIVERGE" in blocked["errors"]
    assert "HISTORY_CANONICAL_COUNTS_CHANGED_DURING_AUDIT" in blocked["errors"]


def test_unclassified_global_blocker_is_not_ignored(tmp_path):
    _, evidence_path, manifest, archive, checksum = _verify(tmp_path)
    report = json.loads(evidence_path.read_text(encoding="utf-8"))
    report["blockers"].append("UNRELATED_GLOBAL_BLOCKER")
    evidence_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")

    blocked = _load_gate().verify(evidence_path, manifest, archive, checksum, DEPLOYED_SHA)
    assert blocked["status"] == "NOT_PROVEN"
    assert "HISTORY_BLOCKERS_NOT_EXACTLY_SCOPED_TO_NON_TARGET_NOT_PROVEN_ROWS" in blocked["errors"]


def test_non_target_identity_failure_is_not_waived_as_historical_incompleteness(tmp_path):
    _, evidence_path, manifest, archive, checksum = _verify(tmp_path)
    report = json.loads(evidence_path.read_text(encoding="utf-8"))
    row = next(item for item in report["requests"] if item["request_id"] == f"{13:032x}")
    row["canonical_round_binding_status"] = "FAIL"
    evidence_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")

    blocked = _load_gate().verify(evidence_path, manifest, archive, checksum, DEPLOYED_SHA)
    assert blocked["status"] == "NOT_PROVEN"
    assert "HISTORY_13_CANONICAL_ROUND_BINDING_STATUS_NOT_PASS" in blocked["errors"]


def test_release_manifest_declares_targeted_and_historical_scope_separately():
    manifest = json.loads(
        (ROOT / "HOTFIX164.30_RELEASE_MANIFEST.json").read_text(encoding="utf-8")
    )
    contract = manifest["independent_gate_contract"]
    assert contract["target_count_exactly_two"] is True
    assert contract["targeted_canonical_message_request_round_counts_exactly_two"] is True
    assert contract["full_canonical_history_counts_preserved_and_checked"] is True
    assert contract["non_target_not_proven_rows_must_be_identity_consistent"] is True
    assert contract["non_target_blockers_must_be_exactly_reconstructable"] is True
    assert contract["target_or_historical_integrity_failures_block_closure"] is True
