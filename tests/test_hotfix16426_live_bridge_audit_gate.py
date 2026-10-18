from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from verify_hotfix16426_live_bridge_audit import DEFAULT_REPORT, validate_report


def _report():
    return json.loads(DEFAULT_REPORT.read_text(encoding="utf-8"))


def test_hotfix16426_supplied_deployed_runtime_audit_meets_strict_live_acceptance():
    report = _report()
    assert validate_report(report) == []


def test_hotfix16426_live_acceptance_fails_closed_when_strict_evidence_is_removed():
    report = deepcopy(_report())
    report["strict_live_bridge_proof"]["records"][0]["missing_evidence"] = ["TARGET_HTTP_PAYLOAD_ATTESTATION"]
    errors = validate_report(report)
    assert "STRICT_LIVE_RECORD_1_INCOMPLETE" in errors


def test_hotfix16426_live_acceptance_rejects_duplicate_bridge_hashes():
    report = deepcopy(_report())
    report["target_requests"][1]["bridge_id_hash"] = report["target_requests"][0]["bridge_id_hash"]
    errors = validate_report(report)
    assert "BRIDGE_HASHES_NOT_DISTINCT" in errors
