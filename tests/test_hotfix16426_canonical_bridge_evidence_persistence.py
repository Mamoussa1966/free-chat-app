"""Regression tests for canonical Bridge evidence surviving Streamlit reruns.

These fixtures validate audit/persistence semantics only. They are deliberately
not treated as proof that a live DeepSeek/Gemini provider transaction occurred.
"""
from __future__ import annotations

from copy import deepcopy
import json

from conversation_store import authoritative_snapshot
from conversation_v25_runtime import authoritative_audit
from tests.test_final_closure_bridge_canonical_evidence import _chat
from tests.test_hotfix1649_live_bridge_evidence_export import _strict_bridge_evidence


def _strict_canonical_chat(*, sidecar: bool = False):
    chat = _chat()
    requests = chat["conversation_record"]["requests"]
    round_by_request = {
        row["request_id"]: row
        for row in chat["conversation_record"]["rounds"]
    }
    evidence_store = {}
    for row, bridge_hash in zip(requests, ("1" * 64, "2" * 64)):
        rid = row["request_id"]
        canonical_round_id = round_by_request[rid]["round_id"]
        evidence = _strict_bridge_evidence(rid, int(row["canonical_round_base"]), bridge_hash)
        evidence["schema"] = "bridge-runtime-evidence/v3"
        evidence["canonical_round_id"] = canonical_round_id
        evidence["bridge_trace_count"] = 2
        row["bridge_test_requested"] = True
        row["bridge_runtime_contract"] = "STRICT_LIVE"
        row["bridge_runtime_evidence"] = deepcopy(evidence)
        evidence_store[rid] = deepcopy(evidence)
    chat["bridge_runtime_evidence_store"] = evidence_store if sidecar else {}
    return chat


def test_hotfix16426_strict_live_audit_recovers_canonical_evidence_after_sidecar_loss():
    chat = _strict_canonical_chat(sidecar=False)
    audit = authoritative_audit(chat)
    assert audit["bridge_runtime_proof_status_message_1"] == "PASS"
    assert audit["bridge_runtime_proof_status_message_2"] == "PASS"
    assert audit["bridge_history_proven"] is True
    assert audit["conversation_runtime_audit"] == "PASS"


def test_hotfix16426_sidecar_only_evidence_never_proves_strict_live_bridge():
    chat = _strict_canonical_chat(sidecar=True)
    for row in chat["conversation_record"]["requests"]:
        row.pop("bridge_runtime_evidence", None)
    audit = authoritative_audit(chat)
    assert audit["bridge_runtime_proof_status_message_1"] == "NOT_PROVEN"
    assert audit["bridge_runtime_proof_status_message_2"] == "NOT_PROVEN"
    assert audit["bridge_history_proven"] is False
    assert audit["conversation_runtime_audit"] == "NOT_PROVEN"


def test_hotfix16426_conflicting_sidecar_cannot_override_canonical_evidence():
    chat = _strict_canonical_chat(sidecar=True)
    rid = chat["conversation_record"]["requests"][0]["request_id"]
    chat["bridge_runtime_evidence_store"][rid]["bridge_id_hash"] = "f" * 64
    audit = authoritative_audit(chat)
    assert audit["bridge_runtime_proof_status_message_1"] == "NOT_PROVEN"
    assert audit["bridge_history_proven"] is False


def test_hotfix16426_export_uses_canonical_evidence_when_runtime_cache_is_empty():
    chat = _strict_canonical_chat(sidecar=False)
    snapshot = authoritative_snapshot(chat)
    exported = snapshot["bridge_runtime_evidence_export"]
    assert exported["authoritative_source"] == "APPLICATION_OWNED_RUNTIME_RECORDS_ONLY"
    assert exported["status"] == "PASS"
    assert exported["request_count"] == 2
    assert {row["request_id"] for row in exported["records"]} == {"r1", "r2"}
    serialized = json.dumps(snapshot, sort_keys=True)
    assert "CANARY" not in serialized
    assert '"bridge_id": "[REDACTED]"' in serialized
