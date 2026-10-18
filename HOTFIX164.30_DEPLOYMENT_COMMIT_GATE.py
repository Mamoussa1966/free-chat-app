#!/usr/bin/env python3
"""Independent fail-closed verifier for a fresh HOTFIX164.30 live Bridge report.

This script verifies an application-exported report, its identity binding, safe
HTTP-body attestations, release manifest, archive contents, and archive checksum.
It never calls a provider API and never turns absent evidence into a pass.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile
from datetime import timedelta

from hotfix16430_deployment_attestation import compute_source_bundle

EXPECTED_RELEASE = "HOTFIX164.30"
EXPECTED_CORE = "V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE"
EXPECTED_REPORT_SCHEMA = "hotfix164.23-explicit-target-read-only-forensics/v1"
EXPECTED_ATTESTATION_SCHEMA = "hotfix164.30-runtime-http-attestation/v1"
EXPECTED_BOUNDARY = "requests.PreparedRequest.body"
EXPECTED_PHASES = ["SOURCE_EXECUTION", "WRITE", "VALIDATE", "COMMIT", "BARRIER", "TARGET_DISPATCH", "TARGET_RESPONSE", "READ", "MATCH"]
EXPECTED_EVENT_STATUSES = ["SUCCESS", "RECORDED", "PASS", "PASS", "PASS", "ACCEPTED", "SUCCESS", "PASS", "PASS"]
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SHA40 = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
ROOT = Path(__file__).resolve().parent
EXPECTED_APP_IDENTITY = "HOTFIX164.30 — DEPLOYED-COMMIT-BOUND LIVE CLOSURE"


def _load_json(path: Path, label: str, errors: list[str]) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            errors.append(f"{label}_NOT_JSON_OBJECT")
            return {}
        return value
    except FileNotFoundError:
        errors.append(f"{label}_MISSING:{path}")
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{label}_UNREADABLE:{type(exc).__name__}")
    return {}


def _eq(obj: dict, key: str, expected, prefix: str, errors: list[str]) -> None:
    if obj.get(key) != expected:
        errors.append(f"{prefix}_{key.upper()}_MISMATCH")


def _check_attestation(row: dict, rid: str, round_id: str, ordinal: int, errors: list[str]) -> None:
    prefix = f"TARGET_{ordinal}"
    att = row.get("runtime_http_attestation")
    if not isinstance(att, dict):
        errors.append(f"{prefix}_HTTP_ATTESTATION_MISSING")
        return
    _eq(att, "schema", EXPECTED_ATTESTATION_SCHEMA, prefix, errors)
    _eq(att, "request_id", rid, prefix, errors)
    _eq(att, "canonical_round_id", round_id, prefix, errors)
    _eq(att, "canonical_round_ordinal", str(ordinal), prefix, errors)
    _eq(att, "source_provider", "DeepSeek", prefix, errors)
    _eq(att, "source_seat", "7", prefix, errors)
    _eq(att, "target_provider", "Gemini", prefix, errors)
    _eq(att, "target_seat", "2", prefix, errors)
    _eq(att, "transport_boundary", EXPECTED_BOUNDARY, prefix, errors)
    _eq(att, "prepared_request_verified", "YES", prefix, errors)
    _eq(att, "payload_hash_integrity", "PASS", prefix, errors)
    _eq(att, "http_payload_attested", "YES", prefix, errors)
    for field in (
        "request_binding_status", "round_binding_status", "target_binding_status",
        "response_binding_status", "canonical_round_binding_status",
    ):
        _eq(att, field, "PASS", prefix, errors)
    for field in (
        "runtime_sequence_valid", "source_execution_proven", "write_status", "validate_status",
        "commit_status", "barrier_status", "target_dispatch_status", "target_response_status",
        "read_status", "match_status", "sanitized_representation_only", "application_owned",
        "bridge_gate_status",
    ):
        _eq(att, field, "PASS", prefix, errors)
    _eq(att, "terminal_state", "COMMITTED", prefix, errors)
    _eq(att, "bridge_state_terminal", "COMMITTED", prefix, errors)
    if not HEX64.fullmatch(str(att.get("payload_sha256") or "").lower()):
        errors.append(f"{prefix}_HTTP_PAYLOAD_SHA256_INVALID")
    if not HEX64.fullmatch(str(att.get("endpoint_sha256") or "").lower()):
        errors.append(f"{prefix}_HTTP_ENDPOINT_SHA256_INVALID")
    try:
        if int(att.get("payload_bytes") or 0) <= 0:
            errors.append(f"{prefix}_HTTP_PAYLOAD_BYTES_INVALID")
    except (TypeError, ValueError):
        errors.append(f"{prefix}_HTTP_PAYLOAD_BYTES_INVALID")
    if not str(att.get("executed_model") or "").strip() or att.get("executed_model") == "NOT_PROVEN":
        errors.append(f"{prefix}_EXECUTED_MODEL_NOT_PROVEN")
    for field in (
        "user_prompt_contains_value", "target_prompt_contains_value", "http_payload_contains_value",
        "http_payload_contains_bridge_key", "http_payload_contains_bridge_id",
        "http_payload_contains_request_id", "http_payload_contains_canonical_round_id",
        "user_prompt_contains_bridge_id", "provider_prompt_contains_bridge_id",
        "target_prompt_contains_bridge_id", "target_prompt_contains_bridge_key",
        "target_prompt_contains_request_id", "target_prompt_contains_canonical_round_id",
        "control_plane_identity_leak",
    ):
        _eq(att, field, "NO", prefix, errors)
    for field in ("raw_payload_exported", "raw_prompt_exported", "raw_bridge_value_exported", "raw_bridge_id_exported"):
        _eq(att, field, False, prefix, errors)

    sequence = att.get("phase_sequence")
    _eq(att, "expected_phase_sequence", EXPECTED_PHASES, prefix, errors)
    if not isinstance(sequence, list) or len(sequence) != len(EXPECTED_PHASES):
        errors.append(f"{prefix}_HTTP_ATTESTED_PHASE_SEQUENCE_INCOMPLETE")
        return
    phases = []
    for index, event in enumerate(sequence):
        if not isinstance(event, dict):
            errors.append(f"{prefix}_PHASE_EVENT_{index+1}_INVALID")
            continue
        phases.append(event.get("phase"))
        if event.get("seq") != index + 1:
            errors.append(f"{prefix}_PHASE_EVENT_{index+1}_SEQUENCE_MISMATCH")
        if event.get("status") != EXPECTED_EVENT_STATUSES[index]:
            errors.append(f"{prefix}_PHASE_EVENT_{index+1}_STATUS_MISMATCH")
        for field in ("request_identity_status", "round_identity_status", "role_identity_status"):
            if event.get(field) != "PASS":
                errors.append(f"{prefix}_PHASE_EVENT_{index+1}_{field.upper()}_NOT_PASS")
    if phases != EXPECTED_PHASES:
        errors.append(f"{prefix}_PHASE_ORDER_MISMATCH")


def verify(evidence_path: Path, manifest_path: Path, archive_path: Path, checksum_path: Path | None = None, expected_commit_sha: str | None = None) -> dict:
    errors: list[str] = []
    evidence = _load_json(evidence_path, "LIVE_EVIDENCE", errors)
    manifest = _load_json(manifest_path, "RELEASE_MANIFEST", errors)

    _eq(manifest, "release", EXPECTED_RELEASE, "MANIFEST", errors)
    _eq(manifest, "provider_core_identity", EXPECTED_CORE, "MANIFEST", errors)
    if (manifest.get("bridge_closure_contract") or {}).get("live_final_closure_proven") is not False:
        errors.append("MANIFEST_MUST_NOT_PRECLAIM_LIVE_CLOSURE")
    if (manifest.get("guardrails") or {}).get("version_txt_contract_preserved") is not True:
        errors.append("MANIFEST_VERSION_GUARDRAIL_NOT_PASS")

    if not archive_path.is_file():
        errors.append(f"RELEASE_ARCHIVE_MISSING:{archive_path}")
        archive_sha = ""
    else:
        archive_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        if checksum_path is not None:
            try:
                raw = checksum_path.read_text(encoding="utf-8")
                expected = f"{archive_sha}  {archive_path.name}\n"
                if raw != expected:
                    errors.append("RELEASE_ARCHIVE_SHA256_SIDECAR_MISMATCH")
            except OSError:
                errors.append("RELEASE_ARCHIVE_SHA256_SIDECAR_MISSING")
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                names = zf.namelist()
                if len(names) != len(set(names)):
                    errors.append("RELEASE_ARCHIVE_DUPLICATE_MEMBERS")
                required = {
                    "VERSION.txt", "providers.py", "main.py", "HOTFIX164.30_RELEASE_MANIFEST.json",
                    "HOTFIX164.30_DEPLOYMENT_COMMIT_GATE.py", "hotfix16430_deployment_attestation.py", ".github/workflows/hotfix164-30-deployment-commit-closure.yml",
                }
                missing = sorted(required - set(names))
                if missing:
                    errors.append("RELEASE_ARCHIVE_REQUIRED_FILES_MISSING:" + ",".join(missing))
                if any(name.lower().endswith(".zip") for name in names):
                    errors.append("RELEASE_ARCHIVE_CONTAINS_NESTED_ZIP")
                try:
                    core = zf.read("VERSION.txt").decode("utf-8").strip()
                    if core != EXPECTED_CORE:
                        errors.append("ARCHIVE_FROZEN_PROVIDER_IDENTITY_MISMATCH")
                    provider_source = zf.read("providers.py").decode("utf-8")
                    if not re.search(r'CURRENT_HOTFIX_RELEASE_VERSION\s*=\s*[\"\']HOTFIX164\.29\s', provider_source):
                        errors.append("ARCHIVE_APP_RELEASE_LABEL_MISMATCH")
                    embedded_manifest = zf.read("HOTFIX164.30_RELEASE_MANIFEST.json")
                    if embedded_manifest != manifest_path.read_bytes():
                        errors.append("ARCHIVE_EMBEDDED_MANIFEST_MISMATCH")
                except (KeyError, OSError, UnicodeDecodeError):
                    errors.append("ARCHIVE_IDENTITY_FILES_UNREADABLE")
        except (OSError, zipfile.BadZipFile):
            errors.append("RELEASE_ARCHIVE_INVALID_ZIP")

    # Independent evidence checks: the old HOTFIX164.28 report cannot pass because
    # it lacks this release identity and request-bound HTTP attestation envelope.
    _eq(evidence, "schema", EXPECTED_REPORT_SCHEMA, "EVIDENCE", errors)
    _eq(evidence, "status", "PASS", "EVIDENCE", errors)
    _eq(evidence, "mode", "READ_ONLY_EXPLICIT_TARGETS", "EVIDENCE", errors)
    _eq(evidence, "read_only", True, "EVIDENCE", errors)
    _eq(evidence, "application_release_identity", "HOTFIX164.30 — DEPLOYED-COMMIT-BOUND LIVE CLOSURE", "EVIDENCE", errors)
    _eq(evidence, "provider_core_identity", EXPECTED_CORE, "EVIDENCE", errors)
    _eq(evidence, "security_audit_status", "PASS", "EVIDENCE", errors)
    _eq(evidence, "canonical_counter_consistent", True, "EVIDENCE", errors)
    _eq(evidence, "canonical_identity_chain_valid", True, "EVIDENCE", errors)
    _eq(evidence, "canonical_history_hash_stable_during_audit", True, "EVIDENCE", errors)
    _eq(evidence, "live_state_unchanged", True, "EVIDENCE", errors)
    _eq(evidence, "read_side_effects", "NONE_OBSERVED", "EVIDENCE", errors)
    _eq(evidence, "read_only_side_effects", "NONE_OBSERVED", "EVIDENCE", errors)
    _eq(evidence, "provider_execution", 0, "EVIDENCE", errors)
    _eq(evidence, "cascade_execution", 0, "EVIDENCE", errors)
    for field in ("new_requests", "new_rounds", "new_bridges"):
        _eq(evidence, field, 0, "EVIDENCE", errors)
    _eq(evidence, "canonical_counts", {"canonical_message_count": 2, "canonical_request_count": 2, "canonical_round_count": 2}, "EVIDENCE", errors)
    if not HEX64.fullmatch(str(evidence.get("audit_active_chat_binding_sha256") or "").lower()):
        errors.append("EVIDENCE_ACTIVE_CHAT_BINDING_HASH_INVALID")
    if evidence.get("blockers") != []:
        errors.append("EVIDENCE_BLOCKERS_NOT_EMPTY")

    generated = str(evidence.get("report_generated_at") or "")
    try:
        ts = datetime.fromisoformat(generated.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            errors.append("EVIDENCE_TIMESTAMP_MISSING_TIMEZONE")
        else:
            age_seconds = (datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds()
            if age_seconds < -300 or age_seconds > 24 * 3600:
                errors.append("EVIDENCE_TIMESTAMP_OUTSIDE_24_HOUR_WINDOW")
    except ValueError:
        errors.append("EVIDENCE_TIMESTAMP_INVALID_OR_MISSING")

    targets = evidence.get("target_requests")
    target_ids = evidence.get("target_request_ids")
    if not isinstance(targets, list) or len(targets) != 2:
        errors.append("EVIDENCE_MUST_HAVE_EXACTLY_TWO_TARGET_ROWS")
        targets = []
    if not isinstance(target_ids, list) or len(target_ids) != 2 or len(set(str(x) for x in target_ids)) != 2:
        errors.append("EVIDENCE_TARGET_REQUEST_IDS_NOT_TWO_DISTINCT_IDS")
        target_ids = target_ids if isinstance(target_ids, list) else []
    _eq(evidence, "target_request_count", 2, "EVIDENCE", errors)
    _eq(evidence, "target_selection_status", "EXPLICIT_TARGETS_SELECTED", "EVIDENCE", errors)
    request_rows = evidence.get("requests") if isinstance(evidence.get("requests"), list) else []
    request_by_id = {str(x.get("request_id") or ""): x for x in request_rows if isinstance(x, dict)}
    strict = evidence.get("strict_live_bridge_proof") if isinstance(evidence.get("strict_live_bridge_proof"), dict) else {}
    _eq(strict, "status", "PASS", "STRICT_PROOF", errors)
    _eq(strict, "request_count", 2, "STRICT_PROOF", errors)
    for field in ("raw_bridge_id_exported", "raw_bridge_value_exported", "raw_prompt_or_http_body_exported"):
        _eq(strict, field, False, "STRICT_PROOF", errors)
    proof_rows = strict.get("records") if isinstance(strict.get("records"), list) else []
    proof_by_id = {str(x.get("request_id") or ""): x for x in proof_rows if isinstance(x, dict)}
    bridge_hashes = []
    round_ids = []
    seen_ids = []
    for slot, row in enumerate(targets, start=1):
        if not isinstance(row, dict):
            errors.append(f"TARGET_{slot}_ROW_INVALID")
            continue
        rid = str(row.get("request_id") or "").strip()
        seen_ids.append(rid)
        if rid != str(target_ids[slot-1] if slot <= len(target_ids) else ""):
            errors.append(f"TARGET_{slot}_REQUEST_ID_ORDER_MISMATCH")
        _eq(row, "target_slot", slot, f"TARGET_{slot}", errors)
        _eq(row, "status", "PASS", f"TARGET_{slot}", errors)
        _eq(row, "canonical_request_status", "PASS", f"TARGET_{slot}", errors)
        _eq(row, "message_request_binding_status", "PASS", f"TARGET_{slot}", errors)
        _eq(row, "canonical_round_binding_status", "PASS", f"TARGET_{slot}", errors)
        _eq(row, "required_request_artifacts_status", "PASS", f"TARGET_{slot}", errors)
        _eq(row, "bridge_projection_binding_status", "PASS", f"TARGET_{slot}", errors)
        _eq(row, "bridge_request_round_binding_status", "PASS", f"TARGET_{slot}", errors)
        _eq(row, "bridge_proof_status", "PASS", f"TARGET_{slot}", errors)
        _eq(row, "missing_evidence", [], f"TARGET_{slot}", errors)
        _eq(row, "failure_reasons", [], f"TARGET_{slot}", errors)
        _eq(row, "bridge_runtime_evidence_record_count_for_request", 1, f"TARGET_{slot}", errors)
        _eq(row, "bridge_projection_record_count_for_request", 1, f"TARGET_{slot}", errors)
        round_id = str(row.get("canonical_round_id") or "")
        round_ids.append(round_id)
        _eq(row, "canonical_round_ordinal", str(slot), f"TARGET_{slot}", errors)
        bridge_hash = str(row.get("bridge_id_hash") or "").lower()
        bridge_hashes.append(bridge_hash)
        if not HEX64.fullmatch(bridge_hash):
            errors.append(f"TARGET_{slot}_BRIDGE_ID_HASH_INVALID")
        req = request_by_id.get(rid)
        if not isinstance(req, dict):
            errors.append(f"TARGET_{slot}_REQUEST_DIAGNOSTIC_MISSING")
        else:
            _eq(req, "status", "PASS", f"TARGET_{slot}_REQUEST_DIAGNOSTIC", errors)
            _eq(req, "request_execution_status", "PASS", f"TARGET_{slot}_REQUEST_DIAGNOSTIC", errors)
            _eq(req, "execution_identity_status", "PASS", f"TARGET_{slot}_REQUEST_DIAGNOSTIC", errors)
            _eq(req, "canonical_round_binding_status", "PASS", f"TARGET_{slot}_REQUEST_DIAGNOSTIC", errors)
            _eq(req, "strict_live_bridge_status", "PASS", f"TARGET_{slot}_REQUEST_DIAGNOSTIC", errors)
            _eq(req, "missing_required_artifacts", [], f"TARGET_{slot}_REQUEST_DIAGNOSTIC", errors)
            if req.get("execution_started_count", 0) < 1 or req.get("actual_model_attestation_present") is not True:
                errors.append(f"TARGET_{slot}_EXECUTION_NOT_PROVEN")
            required_artifacts = req.get("required_artifacts")
            if not isinstance(required_artifacts, dict) or any(v != "PASS" for v in required_artifacts.values()):
                errors.append(f"TARGET_{slot}_REQUIRED_REQUEST_ARTIFACTS_NOT_PASS")
        proof = proof_by_id.get(rid)
        if not isinstance(proof, dict):
            errors.append(f"TARGET_{slot}_STRICT_PROOF_RECORD_MISSING")
        else:
            _eq(proof, "status", "PASS", f"TARGET_{slot}_STRICT_PROOF", errors)
            _eq(proof, "request_identity_status", "PASS", f"TARGET_{slot}_STRICT_PROOF", errors)
            _eq(proof, "canonical_round_binding_status", "PASS", f"TARGET_{slot}_STRICT_PROOF", errors)
            _eq(proof, "evidence_record_present", True, f"TARGET_{slot}_STRICT_PROOF", errors)
            _eq(proof, "missing_evidence", [], f"TARGET_{slot}_STRICT_PROOF", errors)
            _eq(proof, "failure_reasons", [], f"TARGET_{slot}_STRICT_PROOF", errors)
        _check_attestation(row, rid, round_id, slot, errors)

    if len(set(seen_ids)) != 2:
        errors.append("TARGET_REQUEST_IDS_NOT_UNIQUE")
    if len(set(round_ids)) != 2 or any(not rid for rid in round_ids):
        errors.append("CANONICAL_ROUND_IDS_NOT_UNIQUE_OR_MISSING")
    if len(set(bridge_hashes)) != 2:
        errors.append("BRIDGE_IDS_NOT_UNIQUE")
    if evidence.get("target_bridge_independence_status") != "PASS":
        errors.append("TARGET_BRIDGE_INDEPENDENCE_NOT_PASS")
    if evidence.get("canonical_request_ids_count") != 2 or evidence.get("persisted_request_record_count") != 2:
        errors.append("CANONICAL_AND_PERSISTED_REQUEST_COUNTS_NOT_TWO")
    if evidence.get("request_diagnostic_count") != 2 or evidence.get("execution_started_count") < 2:
        errors.append("REQUEST_DIAGNOSTIC_OR_EXECUTION_COUNTS_INVALID")

    # HOTFIX164.30: the exported forensic report must carry a fresh source-tree
    # fingerprint generated by the running deployed application, not only a copied
    # historical Bridge report. The workflow checks out the commit reported by the
    # app (or an explicitly supplied commit only when the host exposes no SHA).
    deploy = evidence.get("deployment_attestation")
    if not isinstance(deploy, dict):
        errors.append("DEPLOYMENT_ATTESTATION_MISSING")
        deploy = {}
    _eq(deploy, "schema", "hotfix164.30-deployment-source-attestation/v1", "DEPLOYMENT", errors)
    _eq(deploy, "repository", "Mamoussa1966/free-chat-app", "DEPLOYMENT", errors)
    _eq(deploy, "expected_deployment_branch", "gitops-v0.4-final", "DEPLOYMENT", errors)
    _eq(deploy, "application_release_identity", EXPECTED_APP_IDENTITY, "DEPLOYMENT", errors)
    _eq(deploy, "provider_core_identity", EXPECTED_CORE, "DEPLOYMENT", errors)
    _eq(deploy, "source_bundle_complete", True, "DEPLOYMENT", errors)
    _eq(deploy, "read_only", True, "DEPLOYMENT", errors)
    _eq(deploy, "provider_api_calls_made", 0, "DEPLOYMENT", errors)
    _eq(deploy, "raw_payload_exported", False, "DEPLOYMENT", errors)
    _eq(deploy, "secrets_exported", False, "DEPLOYMENT", errors)
    if deploy.get("missing_source_files") != []:
        errors.append("DEPLOYMENT_SOURCE_BUNDLE_INCOMPLETE")
    observed_commit = str(deploy.get("observed_git_commit_sha") or "NOT_AVAILABLE").lower()
    if observed_commit != "not_available" and not SHA40.fullmatch(observed_commit):
        errors.append("DEPLOYMENT_OBSERVED_COMMIT_SHA_INVALID")
    selected_commit = str(expected_commit_sha or observed_commit or "").strip().lower()
    if not SHA40.fullmatch(selected_commit):
        errors.append("DEPLOYMENT_EXPECTED_COMMIT_SHA_MISSING_OR_INVALID")
    if SHA40.fullmatch(observed_commit) and SHA40.fullmatch(selected_commit) and observed_commit != selected_commit:
        errors.append("DEPLOYMENT_OBSERVED_COMMIT_DIFFERS_FROM_CHECKED_OUT_COMMIT")

    generated_deploy = str(deploy.get("generated_at_utc") or "")
    try:
        dep_ts = datetime.fromisoformat(generated_deploy.replace("Z", "+00:00"))
        if dep_ts.tzinfo is None:
            errors.append("DEPLOYMENT_TIMESTAMP_MISSING_TIMEZONE")
        else:
            age = (datetime.now(timezone.utc) - dep_ts.astimezone(timezone.utc)).total_seconds()
            if age < -120 or age > 30 * 60:
                errors.append("DEPLOYMENT_ATTESTATION_NOT_FRESH_WITHIN_30_MINUTES")
    except ValueError:
        errors.append("DEPLOYMENT_TIMESTAMP_INVALID_OR_MISSING")

    local_bundle = compute_source_bundle(ROOT)
    if local_bundle.get("source_bundle_complete") is not True:
        errors.append("CHECKED_OUT_SOURCE_BUNDLE_INCOMPLETE")
    _eq(deploy, "source_bundle_sha256", local_bundle.get("source_bundle_sha256"), "DEPLOYMENT", errors)
    if deploy.get("source_file_sha256") != local_bundle.get("source_file_sha256"):
        errors.append("DEPLOYMENT_SOURCE_FILE_HASH_MAP_MISMATCH")
    bundle_hash = str(deploy.get("source_bundle_sha256") or "").lower()
    if not HEX64.fullmatch(bundle_hash):
        errors.append("DEPLOYMENT_SOURCE_BUNDLE_SHA256_INVALID")
    if deploy.get("commit_binding_status") != "SOURCE_BUNDLE_READY":
        errors.append("DEPLOYMENT_COMMIT_BINDING_NOT_READY")

    result = {
        "schema": "hotfix164.30-independent-closure-result/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "release": EXPECTED_RELEASE,
        "status": "PASS" if not errors else "NOT_PROVEN",
        "live_final_closure_proven": not errors,
        "authoritative_source": "FRESH_APPLICATION_OWNED_READ_ONLY_REPORT_PLUS_INDEPENDENT_RELEASE_AND_HTTP_ATTESTATION_CHECKS",
        "evidence_path": str(evidence_path),
        "evidence_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest() if evidence_path.is_file() else "NOT_PROVEN",
        "release_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest() if manifest_path.is_file() else "NOT_PROVEN",
        "release_archive": str(archive_path),
        "release_archive_sha256": archive_sha,
        "provider_core_identity": EXPECTED_CORE,
        "verified_deployed_commit_sha": selected_commit if SHA40.fullmatch(selected_commit) else "NOT_PROVEN",
        "observed_deployed_commit_sha": observed_commit,
        "deployment_source_bundle_sha256": str(deploy.get("source_bundle_sha256") or "NOT_PROVEN"),
        "deployment_commit_binding_method": "EXACT_GIT_COMMIT_AND_SOURCE_BUNDLE" if observed_commit == selected_commit and SHA40.fullmatch(selected_commit) else ("SOURCE_BUNDLE_MATCH_WITH_EXPLICIT_COMMIT" if SHA40.fullmatch(selected_commit) else "NOT_PROVEN"),
        "target_request_count": 2 if not errors else len(targets),
        "target_request_ids": [str(x) for x in target_ids],
        "errors": sorted(set(errors)),
        "provider_api_calls_made_by_gate": 0,
        "gate_is_read_only": True,
    }
    return result


def write_verified_manifest(manifest_path: Path, output_path: Path, result: dict) -> bool:
    """Write a detached closure manifest only after the independent gate passes."""
    if result.get("status") != "PASS" or result.get("live_final_closure_proven") is not True:
        try:
            output_path.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        output_path.unlink(missing_ok=True)
        return False
    closure = manifest.setdefault("bridge_closure_contract", {})
    closure["live_final_closure_proven"] = True
    closure["status"] = "PASS — independently verified against fresh deployed A/B evidence and exact candidate archive"
    closure["verified_evidence_sha256"] = result.get("evidence_sha256")
    closure["verified_candidate_archive_sha256"] = result.get("release_archive_sha256")
    closure["verified_candidate_manifest_sha256"] = result.get("release_manifest_sha256")
    guardrails = manifest.setdefault("guardrails", {})
    guardrails["live_final_closure_proven"] = True
    manifest["verified_closure_attestation"] = {
        "schema": "hotfix164.30-verified-release-manifest/v1",
        "status": "PASS",
        "live_final_closure_proven": True,
        "verified_at_utc": result.get("generated_at_utc"),
        "independent_gate_schema": result.get("schema"),
        "evidence_sha256": result.get("evidence_sha256"),
        "candidate_archive": result.get("release_archive"),
        "candidate_archive_sha256": result.get("release_archive_sha256"),
        "candidate_manifest_sha256": result.get("release_manifest_sha256"),
        "provider_core_identity": result.get("provider_core_identity"),
        "target_request_count": result.get("target_request_count"),
        "target_request_ids": result.get("target_request_ids"),
        "independent_gate_errors": [],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, type=Path, help="Fresh HOTFIX164.30_BRIDGE_EVIDENCE_FORENSICS.json from the deployed app")
    parser.add_argument("--manifest", default=Path("HOTFIX164.30_RELEASE_MANIFEST.json"), type=Path)
    parser.add_argument("--zip", required=True, type=Path, help="The exact release candidate ZIP to verify")
    parser.add_argument("--sha256", type=Path, help="Detached SHA-256 sidecar for the exact ZIP")
    parser.add_argument("--expected-commit", required=True, help="Exact commit checked out from the deployment attestation")
    parser.add_argument("--output", default=Path("HOTFIX164.30_INDEPENDENT_CLOSURE_RESULT.json"), type=Path)
    parser.add_argument("--verified-manifest-output", type=Path, help="Optional detached verified manifest, created only on PASS")
    args = parser.parse_args()
    result = verify(args.evidence, args.manifest, args.zip, args.sha256, args.expected_commit)
    if args.verified_manifest_output is not None:
        if write_verified_manifest(args.manifest, args.verified_manifest_output, result):
            result["verified_manifest_status"] = "WRITTEN_AFTER_PASS"
            result["verified_manifest_path"] = str(args.verified_manifest_output)
        else:
            result["verified_manifest_status"] = "NOT_WRITTEN"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
