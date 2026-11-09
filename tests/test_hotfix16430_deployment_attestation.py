from __future__ import annotations

import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

from hotfix16430_deployment_attestation import (
    SOURCE_FILES,
    _linux_process_started_at_utc,
    compute_source_bundle,
    build_runtime_deployment_attestation,
)

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
    assert report["process_start_time_status"] in {"PASS", "NOT_PROVEN"}
    if report["process_start_time_status"] == "PASS":
        assert report["process_id"] > 0
        started = datetime.fromisoformat(report["process_started_at_utc"].replace("Z", "+00:00"))
        generated = datetime.fromisoformat(report["generated_at_utc"])
        assert started.tzinfo is not None
        assert started <= generated.replace(tzinfo=timezone.utc)
        assert report["process_started_at_source"] == "linux_procfs"
        assert report["process_uptime_seconds_at_attestation"] >= 0
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



def test_linux_process_start_time_uses_procfs_start_ticks_not_attestation_clock(tmp_path):
    proc = tmp_path
    (proc / "self").mkdir(parents=True)
    # After the final ')' in comm: field 3 state, fields 4..21, then
    # field 22 starttime at token index 19.
    tokens = ["S"] + ["0"] * 18 + ["500"]
    (proc / "self" / "stat").write_text("4321 (streamlit python worker) " + " ".join(tokens), encoding="ascii")
    (proc / "uptime").write_text("1000.00 2500.00\n", encoding="ascii")

    started = _linux_process_started_at_utc(
        proc,
        wall_clock_seconds=1_700_000_000.0,
        clock_ticks=100,
    )

    assert started == datetime.fromtimestamp(1_699_999_005.0, timezone.utc)


def test_linux_process_start_time_fails_closed_when_procfs_is_incomplete(tmp_path):
    (tmp_path / "self").mkdir(parents=True)
    (tmp_path / "self" / "stat").write_text("123 (streamlit) S 0 0", encoding="ascii")

    assert _linux_process_started_at_utc(
        tmp_path,
        wall_clock_seconds=1_700_000_000.0,
        clock_ticks=100,
    ) is None
