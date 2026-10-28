"""HOTFIX164.18: expose sanitized per-Request strict Bridge proof outcomes."""
from __future__ import annotations

import json

from production_platform import security_audit
from tests.test_hotfix16410_strict_bridge_security_audit import _chat_with_strict_requests


def test_hotfix16418_sidecar_loss_does_not_hide_canonical_request_proof():
    chat = _chat_with_strict_requests()
    del chat["bridge_runtime_evidence_store"]["req-one"]

    report = security_audit([chat])
    proof = report["strict_live_bridge_proof"]
    rows = {row["request_id"]: row for row in proof["records"]}

    assert report["status"] == "PASS"
    assert report["checks"]["STRICT_LIVE_BRIDGE_EVIDENCE_AUTHORITATIVE_AND_COMPLETE"] is True
    assert proof["status"] == "PASS"
    assert proof["request_count"] == 2
    assert rows["req-one"]["status"] == "PASS"
    assert rows["req-one"]["evidence_record_present"] is True
    assert rows["req-one"]["missing_evidence"] == []
    assert rows["req-two"]["status"] == "PASS"

    # The diagnostic projection must not export hashes, IDs, values, prompts, or HTTP bodies.
    encoded = json.dumps(proof, sort_keys=True)
    assert "bridge_id_hash" not in encoded
    assert "runtime_payload_sha256" not in encoded
    assert "hash-one" not in encoded
    assert "payload_json" not in encoded
    assert '"bridge_secret"' not in encoded
    assert proof["raw_bridge_id_exported"] is False
    assert proof["raw_bridge_value_exported"] is False
    assert proof["raw_prompt_or_http_body_exported"] is False


def test_hotfix16418_missing_canonical_and_sidecar_proof_is_not_promoted_to_pass():
    chat = _chat_with_strict_requests()
    del chat["bridge_runtime_evidence_store"]["req-one"]
    chat["conversation_record"]["requests"][0].pop("bridge_runtime_evidence")

    report = security_audit([chat])
    proof = report["strict_live_bridge_proof"]
    rows = {row["request_id"]: row for row in proof["records"]}

    assert report["status"] == "FAIL"
    assert proof["status"] == "NOT_PROVEN"
    assert rows["req-one"]["status"] == "NOT_PROVEN"
    assert rows["req-one"]["evidence_record_present"] is False
    assert "APPLICATION_OWNED_BRIDGE_RUNTIME_RECORD" in rows["req-one"]["missing_evidence"]


def test_hotfix16418_complete_independent_request_proofs_report_pass():
    chat = _chat_with_strict_requests()
    report = security_audit([chat])
    proof = report["strict_live_bridge_proof"]

    assert report["status"] == "PASS"
    assert proof["status"] == "PASS"
    assert [row["request_id"] for row in proof["records"]] == ["req-one", "req-two"]
    assert all(row["status"] == "PASS" for row in proof["records"])
    assert all(row["canonical_round_binding_status"] == "PASS" for row in proof["records"])


def test_hotfix16418_explicit_prompt_value_leak_reports_fail_for_affected_request():
    chat = _chat_with_strict_requests()
    chat["conversation_record"]["requests"][0]["bridge_runtime_evidence"]["user_prompt_contains_value"] = "YES"

    report = security_audit([chat])
    proof = report["strict_live_bridge_proof"]
    rows = {row["request_id"]: row for row in proof["records"]}

    assert report["status"] == "FAIL"
    assert proof["status"] == "FAIL"
    assert rows["req-one"]["status"] == "FAIL"
    assert "USER_PROMPT_CONTAINS_VALUE" in rows["req-one"]["failure_reasons"]
    assert rows["req-two"]["status"] == "PASS"


def test_hotfix16418_wrong_request_identity_is_explicit_failure():
    chat = _chat_with_strict_requests()
    chat["conversation_record"]["requests"][0]["bridge_runtime_evidence"]["request_id"] = "req-two"

    proof = security_audit([chat])["strict_live_bridge_proof"]
    rows = {row["request_id"]: row for row in proof["records"]}
    assert proof["status"] == "FAIL"
    assert rows["req-one"]["status"] == "FAIL"
    assert rows["req-one"]["request_identity_status"] == "FAIL"
    assert rows["req-one"]["failure_reasons"] == ["REQUEST_ID_MISMATCH"]
