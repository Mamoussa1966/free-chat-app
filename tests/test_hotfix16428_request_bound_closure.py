from __future__ import annotations

import hashlib
import json

import main
from providers import Seat


def _seat(key="gemini", slot=2):
    return Seat(key, "Gemini" if key == "gemini" else "DeepSeek", key, ("API_KEY",), ("FREE_MODELS",), "", key, slot)


def _chat(conversation_id="conversation-a"):
    rid1, rid2 = "request-a", "request-b"
    return {
        "id": conversation_id,
        "conversation_id": conversation_id,
        "conversation_record": {
            "conversation_id": conversation_id,
            "history_hash": "history-v1",
            "messages": [],
            "requests": [{"request_id": rid1}, {"request_id": rid2}],
            "rounds": [
                {"request_id": rid1, "round_id": f"{conversation_id}:{rid1}:r1", "round_number": 1, "ordinal": 1},
                {"request_id": rid2, "round_id": f"{conversation_id}:{rid2}:r2", "round_number": 2, "ordinal": 2},
            ],
        },
        "bridge_runtime_evidence_store": {},
    }


def _bound_report(chat, targets):
    return {
        "target_request_ids": targets,
        "requests": [{"request_id": rid} for rid in targets],
        "target_requests": [{"request_id": rid} for rid in targets],
        "strict_live_bridge_proof": {"records": [{"request_id": rid} for rid in targets]},
        "audit_active_chat_binding_sha256": main._hotfix16428_active_chat_binding(chat),
    }


def test_hotfix16428_rejects_a_prior_pass_from_another_active_conversation():
    first = _chat("conversation-a")
    second = _chat("conversation-b")
    old_report = _bound_report(first, ["request-a", "request-b"])
    assert main._hotfix16428_report_bound_to_active_chat(first, old_report) is True
    assert main._hotfix16428_report_bound_to_active_chat(second, old_report) is False


def test_hotfix16428_rejects_report_targets_absent_from_active_canonical_requests():
    chat = _chat()
    stale_report = _bound_report(chat, ["old-request-1", "old-request-2"])
    assert main._hotfix16428_report_bound_to_active_chat(chat, stale_report) is False


def test_hotfix16428_report_binding_changes_when_canonical_round_or_history_changes():
    chat = _chat()
    before = main._hotfix16428_active_chat_binding(chat)
    chat["conversation_record"]["history_hash"] = "history-v2"
    assert main._hotfix16428_active_chat_binding(chat) != before


def test_hotfix16428_strict_http_attestation_rejects_other_request_round():
    rid = "request-bound-r1"
    bridge = main.SharedContextBridge(request_id=rid, round_no=1, strict_live_source=True)
    bridge._runtime_bridge_evidence["canonical_round_id"] = f"conversation:{rid}:r1"
    payload = json.dumps({"contents": [{"parts": [{"text": "safe prompt"}]}]}, sort_keys=True)
    bridge.record_runtime_payload_attestation(_seat(), {
        "payload_json": payload,
        "payload_sha256": hashlib.sha256(payload.encode()).hexdigest(),
        "transport_boundary": "requests.PreparedRequest.body",
        "prepared_request_verified": True,
        "request_id": "different-request",
        "round_no": 2,
        "seat_key": "gemini",
        "seat_slot": 2,
        "executed_model": "gemini-3.8-flash",
        "transport_response_attached": True,
    })
    checked = bridge._runtime_payload_attestations[2]
    assert checked["request_identity_binding_status"] == "FAIL"
    assert checked["round_identity_binding_status"] == "FAIL"
    assert checked["integrity_valid"] is False


def test_hotfix16428_strict_http_attestation_binds_successful_response_to_same_round():
    rid = "request-bound-r1"
    bridge = main.SharedContextBridge(request_id=rid, round_no=1, strict_live_source=True)
    bridge._runtime_bridge_evidence["canonical_round_id"] = f"conversation:{rid}:r1"
    payload = json.dumps({"contents": [{"parts": [{"text": "safe prompt"}]}]}, sort_keys=True)
    bridge.record_runtime_payload_attestation(_seat(), {
        "payload_json": payload,
        "payload_sha256": hashlib.sha256(payload.encode()).hexdigest(),
        "transport_boundary": "requests.PreparedRequest.body",
        "prepared_request_verified": True,
        "request_id": rid,
        "round_no": 1,
        "seat_key": "gemini",
        "seat_slot": 2,
        "executed_model": "gemini-3.8-flash",
        "transport_response_attached": True,
    })
    checked = bridge._runtime_payload_attestations[2]
    assert checked["request_identity_binding_status"] == "PASS"
    assert checked["round_identity_binding_status"] == "PASS"
    assert checked["target_identity_binding_status"] == "PASS"
    assert checked["transport_response_binding_status"] == "PASS"
    assert checked["canonical_round_binding_status"] == "PASS"
    assert checked["integrity_valid"] is True
