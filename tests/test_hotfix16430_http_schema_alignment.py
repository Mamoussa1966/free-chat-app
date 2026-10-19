from __future__ import annotations

import importlib.util
from pathlib import Path

import main

ROOT = Path(__file__).resolve().parents[1]


def _load_gate():
    path = ROOT / "HOTFIX164.30_DEPLOYMENT_COMMIT_GATE.py"
    spec = importlib.util.spec_from_file_location("hotfix16430_http_schema_alignment_gate", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hotfix16430_gate_expects_the_schema_actually_emitted_by_runtime_exporter():
    exported = main._hotfix16429_export_runtime_http_attestation({}, "request-test", "1")
    gate = _load_gate()

    assert exported["schema"] == "hotfix164.29-runtime-http-attestation/v1"
    assert gate.EXPECTED_ATTESTATION_SCHEMA == exported["schema"]


def test_http_attestation_wire_schema_is_independent_of_release_identity():
    manifest = __import__("json").loads(
        (ROOT / "HOTFIX164.30_RELEASE_MANIFEST.json").read_text(encoding="utf-8")
    )
    assert manifest["report_schema_contract"]["schema_versioned_independently_from_application_release"] is True
    assert manifest["independent_gate_contract"]["runtime_http_attestation_schema"] == (
        "hotfix164.29-runtime-http-attestation/v1"
    )
