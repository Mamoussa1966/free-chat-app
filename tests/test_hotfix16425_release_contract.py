from __future__ import annotations

import json
from pathlib import Path

import main
import providers
from release_identity import OBSERVED_DEPLOYED_IDENTITY, deployed_release_identity

ROOT = Path(__file__).resolve().parents[1]
FROZEN_PROVIDER = "V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE"
REPORT_SCHEMA = "hotfix164.23-explicit-target-read-only-forensics/v1"


def test_hotfix16425_display_release_uses_provider_owned_identity():
    assert providers.CURRENT_HOTFIX_RELEASE_VERSION == (
        "HOTFIX164.26 — CANONICAL BRIDGE EVIDENCE REHYDRATION"
    )
    assert main.DISPLAY_VERSION == providers.CURRENT_HOTFIX_RELEASE_VERSION


def test_hotfix16425_platform_release_uses_single_authoritative_value():
    assert main.PLATFORM_RELEASE_VERSION == providers.PLATFORM_RELEASE_VERSION
    assert OBSERVED_DEPLOYED_IDENTITY["platform_release"] == providers.PLATFORM_RELEASE_VERSION
    report = deployed_release_identity()
    assert report["runtime"]["platform_release"] == providers.PLATFORM_RELEASE_VERSION
    assert report["runtime_matches_frozen_identity"] is True
    assert report["identity_conflict"] is False


def test_hotfix16425_frozen_provider_and_version_file_are_unchanged():
    assert providers.VERSION == FROZEN_PROVIDER
    assert (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip() == FROZEN_PROVIDER


def test_hotfix16425_current_manifest_matches_live_source_contract():
    manifest = json.loads((ROOT / "HOTFIX164.26_RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["release"] == "HOTFIX164.26"
    assert manifest["provider_core_identity"] == providers.VERSION
    assert manifest["release_contract"]["runtime_label_matches_main_display_version"] is True
    assert manifest["release_contract"]["platform_release_identity_single_source"] is True
    assert manifest["report_schema_contract"]["read_only_audit_schema"] == REPORT_SCHEMA
    assert manifest["report_schema_contract"]["wire_contract_changed"] is False
    assert manifest["guardrails"]["version_txt_contract_preserved"] is True


def test_hotfix16425_report_schema_contract_remains_independent_and_fail_closed():
    manifest = json.loads((ROOT / "HOTFIX164.26_RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    chat = {}
    before = dict(chat)
    report = main._hotfix16420_read_only_target_audit(chat, target_request_ids=[])
    assert report["schema"] == REPORT_SCHEMA
    assert report["read_only"] is True
    assert report["status"] in {"NOT_PROVEN", "FAIL"}
    assert report["target_request_count"] == 0
    assert report["new_requests"] == 0
    assert report["new_rounds"] == 0
    assert report["new_bridges"] == 0
    assert chat == before
    assert manifest["bridge_closure_contract"]["live_final_closure_proven"] is False
    assert manifest["bridge_closure_contract"]["missing_or_incomplete_evidence_passes"] is False
    assert "NOT_PROVEN" in manifest["bridge_closure_contract"]["status"]
    assert manifest["bridge_closure_contract"]["prior_explicit_two_request_audit_status"].startswith("PASS previously reported")
    assert manifest["bridge_closure_contract"]["new_or_incomplete_live_evidence_status"] == "NOT_PROVEN"
    assert manifest["bridge_closure_contract"]["canonical_request_record_is_evidence_authority"] is True
    assert manifest["bridge_closure_contract"]["sidecar_only_evidence_satisfies_strict_live"] is False


def test_hotfix16425_missing_canonical_conversation_is_explicitly_not_proven_without_side_effects():
    chat = {}
    before = json.dumps(chat, sort_keys=True)

    report = main._hotfix16420_read_only_target_audit(chat, target_request_ids=[])

    assert report["status"] == "NOT_PROVEN"
    assert "NO_EXISTING_CANONICAL_CONVERSATION" in report["blockers"]
    assert "NO_EXPLICIT_TARGETS_PROVIDED" in report["blockers"]
    assert report["provider_execution"] == report["cascade_execution"] == 0
    assert report["new_requests"] == report["new_rounds"] == report["new_bridges"] == 0
    assert json.dumps(chat, sort_keys=True) == before


def test_hotfix16425_empty_canonical_history_never_qualifies_as_closure():
    chat = {
        "id": "existing-empty-chat",
        "request_records": [],
        "conversation_record": {"messages": [], "requests": [], "rounds": []},
    }
    before = json.dumps(chat, sort_keys=True)

    report = main._hotfix16420_read_only_target_audit(chat, target_request_ids=[])

    assert report["status"] == "NOT_PROVEN"
    assert "CANONICAL_HISTORY_EMPTY_NOT_PROVEN" in report["blockers"]
    assert "NO_EXPLICIT_TARGETS_PROVIDED" in report["blockers"]
    assert report["read_only_live_state_unchanged"] is True
    assert report["provider_execution"] == report["cascade_execution"] == 0
    assert report["new_requests"] == report["new_rounds"] == report["new_bridges"] == 0
    assert json.dumps(chat, sort_keys=True) == before


def test_hotfix16425_current_release_workflow_checks_current_contract():
    workflow = (ROOT / ".github/workflows/hotfix164-18-proof-diagnostics.yml").read_text(encoding="utf-8")
    assert "HOTFIX164.26_RELEASE_MANIFEST.json" in workflow
    assert "HOTFIX164.26_CANONICAL_BRIDGE_EVIDENCE_REHYDRATION.zip" in workflow
    assert "HOTFIX164.26_RUNTIME_LABEL_FAILED" in workflow
    assert "PLATFORM_RELEASE_IDENTITY_FAILED" in workflow
    assert "REPORT_SCHEMA_COMPATIBILITY_FAILED" in workflow


def test_hotfix16419_historical_workflow_is_manual_only():
    workflow = (ROOT / ".github/workflows/hotfix164-19-read-only-forensics.yml").read_text(encoding="utf-8")
    assert "HOTFIX164.19" in workflow
    assert "workflow_dispatch:" in workflow
    assert "  push:" not in workflow
    assert "HISTORICAL_RELEASE_MUST_NOT_BE_ACTIVE" in workflow
    assert "HOTFIX164.25_HISTORICAL_HOTFIX16419_COMPATIBILITY_AUDIT.zip" in workflow
