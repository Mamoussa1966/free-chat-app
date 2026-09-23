import json
from unittest.mock import patch
import main
from production_platform import build_v23_platform_audit


def _success(seat, user_prompt, shared_context, round_no, local_fallback, credential, attachments, candidates, deadline, request_id):
    model = str(candidates[0])
    return {
        "seat": seat.key, "name": seat.name, "label": seat.label,
        "status": "SUCCESS", "mode": "official_api", "content": "ordinary response",
        "request_id": request_id, "round": round_no, "model": model,
        "executed_model": model, "attempted_models": [model],
        "_provider_input_prompt": shared_context,
        "_runtime_payload_attestation": {
            "payload_json": json.dumps({"input": shared_context}, ensure_ascii=False),
            "payload_sha256": "attested",
        },
    }


def test_persistence_style_request_does_not_create_bridge_audit():
    credentials = {k: "TEST" for k in ("deepseek", "gemini", "claude", "grok")}
    models = {k: (f"{k}-model",) for k in credentials}
    chat = {"messages": [], "request_records": []}
    prompt = "V26.3.2 HISTORICAL PERSISTENCE TEST — MESSAGE 1\nQuestion: organize a business meeting."
    with patch.object(main, "call_seat", side_effect=_success):
        results = main._run_round(prompt, chat, 1, credentials, [], models, "msg", None, "RID-NO-BRIDGE")
    assert not any(isinstance(r.get("bridge_transaction_audit"), dict) for r in results)
    assert not any(isinstance(r.get("bridge_security_regression_gate"), dict) for r in results)


def test_requested_bridge_without_authoritative_audit_fails_closed():
    chat = {
        "id": "c", "messages": [],
        "request_records": [{
            "request_id": "RID-BRIDGE-REQUESTED",
            "bridge_test_requested": True,
            "results": [],
        }],
    }
    report = build_v23_platform_audit(
        chat, "RID-BRIDGE-REQUESTED", {"chars": 1, "digest": "x"},
        [{"status": "READY"}], {"status": "PASS"}, {"gate": "PASS"},
    )
    assert report["bridge_isolation"]["requested"] is True
    assert report["bridge_isolation"]["status"] == "FAIL"
    assert report["status"] == "FAIL"


def test_non_requested_bridge_is_neutral_not_failure():
    chat = {
        "id": "c", "messages": [],
        "request_records": [{
            "request_id": "RID-PERSISTENCE",
            "bridge_test_requested": False,
            "results": [],
        }],
    }
    report = build_v23_platform_audit(
        chat, "RID-PERSISTENCE", {"chars": 1, "digest": "x"},
        [{"status": "READY"}], {"status": "PASS"}, {"gate": "PASS"},
    )
    assert report["bridge_isolation"]["requested"] is False
    assert report["bridge_isolation"]["status"] == "NOT_REQUESTED"
    assert report["bridge_isolation"]["status"] == "NOT_REQUESTED"
