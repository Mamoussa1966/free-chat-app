from __future__ import annotations

import hashlib
import json
from pathlib import Path

from hotfix16430_deployment_attestation import SOURCE_FILES, compute_source_bundle, build_runtime_deployment_attestation

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_attestation_contains_all_required_source_hashes_and_no_secrets():
    report = build_runtime_deployment_attestation(ROOT)
    assert report["schema"] == "hotfix164.30-deployment-source-attestation/v1"
    assert report["repository"] == "Mamoussa1966/free-chat-app"
    assert report["application_release_identity"].startswith("HOTFIX164.30 ")
    assert report["provider_core_identity"] == (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip()
    assert report["source_bundle_complete"] is True
    assert report["missing_source_files"] == []
    assert set(report["source_file_sha256"]) == set(SOURCE_FILES)
    assert len(report["source_bundle_sha256"]) == 64
    assert report["raw_payload_exported"] is False
    assert report["secrets_exported"] is False
    serialized = json.dumps(report, sort_keys=True)
    assert "API_KEY" not in serialized
    assert "payload_json" not in serialized


def test_source_bundle_is_deterministic_and_changes_when_required_file_changes(tmp_path):
    root = tmp_path
    for rel in SOURCE_FILES:
        file = root / rel
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("stable:" + rel, encoding="utf-8")
    first = compute_source_bundle(root)
    second = compute_source_bundle(root)
    assert first == second
    assert first["source_bundle_complete"] is True
    assert len(first["source_bundle_sha256"]) == 64
    (root / "main.py").write_text("tampered source", encoding="utf-8")
    changed = compute_source_bundle(root)
    assert changed["source_bundle_sha256"] != first["source_bundle_sha256"]
    assert changed["source_file_sha256"]["main.py"] == hashlib.sha256(b"tampered source").hexdigest()


def test_source_bundle_missing_file_fails_closed(tmp_path):
    for rel in SOURCE_FILES[:-1]:
        file = tmp_path / rel
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("x", encoding="utf-8")
    result = compute_source_bundle(tmp_path)
    assert result["source_bundle_complete"] is False
    assert result["source_bundle_sha256"] == "NOT_PROVEN"
    assert SOURCE_FILES[-1] in result["missing_source_files"]


def test_independent_deployment_gate_fails_closed_when_commit_attestation_is_missing(tmp_path):
    import importlib.util
    gate_path = ROOT / "HOTFIX164.30_DEPLOYMENT_COMMIT_GATE.py"
    spec = importlib.util.spec_from_file_location("hotfix16430_deployment_gate_test", gate_path)
    gate = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(gate)
    evidence = tmp_path / "evidence.json"
    manifest = tmp_path / "manifest.json"
    archive = tmp_path / "candidate.zip"
    checksum = tmp_path / "candidate.zip.sha256"
    evidence.write_text("{}", encoding="utf-8")
    manifest.write_text("{}", encoding="utf-8")
    archive.write_bytes(b"not a zip")
    checksum.write_text("invalid\n", encoding="utf-8")
    result = gate.verify(evidence, manifest, archive, checksum, "a" * 40)
    assert result["status"] == "NOT_PROVEN"
    assert "DEPLOYMENT_ATTESTATION_MISSING" in result["errors"]
    assert result["live_final_closure_proven"] is False
