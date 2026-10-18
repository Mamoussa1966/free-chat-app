from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from verify_hotfix16426_live_bridge_audit import DEFAULT_REPORT, validate_report

OLD_IDS = [
    "274521681c3b49b68bf988c128803b69",
    "317d3f311ffe4ff782eeff2fa4351454",
]
CURRENT_IDS = [
    "6d3429f1dae84863a362e3abbc7aede2",
    "efc1820735ba45ddb9eb04e676ec795a",
]


def _report():
    return json.loads(DEFAULT_REPORT.read_text(encoding="utf-8"))


def test_hotfix16426_accepts_final_corrected_deployed_audit():
    report = _report()
    assert report["status"] == "PASS"
    assert report["blockers"] == []
    assert report["target_request_ids"] == CURRENT_IDS
    assert report["runtime_execution_event_count"] == 4
    assert validate_report(report) == []


def test_hotfix16426_rejects_prior_mistyped_target_ids():
    report = deepcopy(_report())
    report["target_request_ids"] = OLD_IDS
    errors = validate_report(report)
    assert "REQUEST_ROWS_ID_MISMATCH" in errors
    assert "STRICT_LIVE_RECORD_IDS_MISMATCH" in errors
    assert "TARGET_ROWS_ID_MISMATCH" in errors


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


def test_hotfix16426_target_form_does_not_reuse_ids_from_another_run():
    import main
    chat = {"conversation_record": {"requests": [
        {"request_id": CURRENT_IDS[0]},
        {"request_id": CURRENT_IDS[1]},
    ]}}
    assert main._hotfix16426_clear_stale_target_ids(chat, OLD_IDS) == ["", ""]
    assert main._hotfix16426_clear_stale_target_ids(chat, CURRENT_IDS) == CURRENT_IDS
