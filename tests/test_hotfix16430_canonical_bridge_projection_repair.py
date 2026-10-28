"""HOTFIX164.30 regression tests for canonical Bridge evidence and projection repair.

These tests validate only evidence already persisted by the application. They do not
perform provider calls or manufacture live execution records.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import main
from conversation_store import rebuild_bridge_ledger_projection
from production_platform import (
    _strict_live_bridge_evidence_complete,
    _strict_live_bridge_request_diagnostic,
)
from tests.test_hotfix16426_canonical_bridge_evidence_persistence import _strict_canonical_chat


def _fixture():
    chat = _strict_canonical_chat(sidecar=False)
    for request in chat["conversation_record"]["requests"]:
        evidence = request["bridge_runtime_evidence"]
        evidence["canonical_round_ordinal"] = str(request["canonical_round_base"])
    return chat


def test_projection_repair_builds_only_redacted_row_from_bound_canonical_evidence():
    chat = _fixture()
    rid = "r1"
    request = next(row for row in chat["conversation_record"]["requests"] if row["request_id"] == rid)
    result = rebuild_bridge_ledger_projection(chat, rid)

    assert result == {
        "status": "PASS",
        "action": "REBUILT",
        "request_id": rid,
        "round_id": request["bridge_runtime_evidence"]["canonical_round_id"],
    }
    rows = [row for row in chat["bridge_ledger_v24"] if row.get("request_id") == rid]
    assert len(rows) == 1
    assert rows[0]["round_id"] == request["bridge_runtime_evidence"]["canonical_round_id"]
    assert rows[0]["bridge_id_hash"] == request["bridge_runtime_evidence"]["bridge_id_hash"]
    assert rows[0]["projection_only"] is True
    serialized = json.dumps(rows, sort_keys=True)
    assert '"bridge_id"' not in serialized
    assert "BRIDGE_RESULT" not in serialized
    assert "CANARY" not in serialized


def test_projection_repair_is_idempotent_and_does_not_duplicate_rows():
    chat = _fixture()
    first = rebuild_bridge_ledger_projection(chat, "r1")
    second = rebuild_bridge_ledger_projection(chat, "r1")

    assert first["action"] == "REBUILT"
    assert second["status"] == "PASS"
    assert second["action"] == "ALREADY_PRESENT"
    assert sum(row.get("request_id") == "r1" for row in chat["bridge_ledger_v24"]) == 1


def test_projection_repair_rejects_sidecar_only_evidence():
    chat = _fixture()
    request = next(row for row in chat["conversation_record"]["requests"] if row["request_id"] == "r1")
    request.pop("bridge_runtime_evidence")
    chat["bridge_runtime_evidence_store"]["r1"] = {
        "schema": "bridge-runtime-evidence/v3",
        "request_id": "r1",
        "round_id": 1,
        "canonical_round_id": "conv-final:r1:r1",
        "canonical_round_ordinal": "1",
        "bridge_id_hash": "1" * 64,
    }

    result = rebuild_bridge_ledger_projection(chat, "r1")

    assert result["status"] == "NOT_PROVEN"
    assert result["reason"] == "CANONICAL_RUNTIME_EVIDENCE_MISSING"
    assert chat["bridge_ledger_v24"] == []


def test_projection_repair_fails_closed_on_conflicting_existing_row():
    chat = _fixture()
    chat["bridge_ledger_v24"].append({
        "request_id": "r1",
        "round_id": "wrong-round",
        "bridge_id_hash": "f" * 64,
    })

    result = rebuild_bridge_ledger_projection(chat, "r1")

    assert result["status"] == "FAIL"
    assert result["reason"] == "EXISTING_BRIDGE_PROJECTION_CONFLICT"
    assert len(chat["bridge_ledger_v24"]) == 1
    assert chat["bridge_ledger_v24"][0]["round_id"] == "wrong-round"


def test_strict_live_audit_uses_canonical_request_evidence_when_sidecar_is_absent():
    chat = _fixture()
    request = next(row for row in chat["conversation_record"]["requests"] if row["request_id"] == "r1")

    assert chat["bridge_runtime_evidence_store"] == {}
    assert _strict_live_bridge_evidence_complete(chat, request) is True
    diagnostic = _strict_live_bridge_request_diagnostic(chat, request)
    assert diagnostic["evidence_record_present"] is True
    assert diagnostic["request_identity_status"] == "PASS"
    assert diagnostic["canonical_round_binding_status"] == "PASS"
    assert diagnostic["status"] == "PASS"
    assert diagnostic["missing_evidence"] == []


def test_strict_live_audit_rejects_a_conflicting_runtime_cache():
    chat = _fixture()
    request = next(row for row in chat["conversation_record"]["requests"] if row["request_id"] == "r1")
    chat["bridge_runtime_evidence_store"]["r1"] = deepcopy(request["bridge_runtime_evidence"])
    chat["bridge_runtime_evidence_store"]["r1"]["bridge_id_hash"] = "f" * 64

    assert _strict_live_bridge_evidence_complete(chat, request) is False
    diagnostic = _strict_live_bridge_request_diagnostic(chat, request)
    assert diagnostic["status"] == "FAIL"
    assert diagnostic["failure_reasons"] == ["CANONICAL_RUNTIME_EVIDENCE_CACHE_CONFLICT"]



def test_strict_live_audit_does_not_ignore_conflicting_cache_safety_flags():
    chat = _fixture()
    request = next(row for row in chat["conversation_record"]["requests"] if row["request_id"] == "r1")
    chat["bridge_runtime_evidence_store"]["r1"] = deepcopy(request["bridge_runtime_evidence"])
    chat["bridge_runtime_evidence_store"]["r1"]["control_plane_identity_leak"] = "YES"

    assert _strict_live_bridge_evidence_complete(chat, request) is False
    diagnostic = _strict_live_bridge_request_diagnostic(chat, request)
    assert diagnostic["status"] == "FAIL"
    assert diagnostic["failure_reasons"] == ["CANONICAL_RUNTIME_EVIDENCE_CACHE_CONFLICT"]


def test_supabase_presentation_state_never_persists_raw_legacy_bridge_ids():
    chat = {
        "bridge_ledger_v24": [
            {
                "request_id": "r-legacy", "round_id": "c:r-legacy:r1",
                "bridge_id": "RAW_LEGACY_BRIDGE_ID", "status": "PASS",
            },
            {
                "request_id": "r-hash", "round_id": "c:r-hash:r1",
                "bridge_id_hash": "a" * 64, "bridge_id": "RAW_SECOND_BRIDGE_ID",
                "status": "PASS",
            },
            {
                "request_id": "r-bad-hash", "round_id": "c:r-bad-hash:r1",
                "bridge_id_hash": "not-a-valid-hash", "bridge_id": "RAW_CONFLICTING_BRIDGE_ID",
                "status": "PASS",
            },
        ]
    }

    rows = main._safe_bridge_projection_for_storage(chat)

    assert len(rows) == 3
    assert rows[0]["bridge_id_hash"] == hashlib.sha256(b"RAW_LEGACY_BRIDGE_ID").hexdigest()
    assert rows[1]["bridge_id_hash"] == "a" * 64
    assert rows[2]["bridge_id_hash"] == "NOT_PROVEN"
    assert rows[2]["status"] == "NOT_PROVEN"
    assert all("bridge_id" not in row for row in rows)
    serialized = json.dumps(rows, sort_keys=True)
    assert "RAW_LEGACY_BRIDGE_ID" not in serialized
    assert "RAW_SECOND_BRIDGE_ID" not in serialized
    assert "RAW_CONFLICTING_BRIDGE_ID" not in serialized

