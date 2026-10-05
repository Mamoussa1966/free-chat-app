import main
from providers import Seat
from conversation_store import canonical_upsert_request, canonical_identity_counts


def _seat(key, name, slot):
    return Seat(key, name, name, (f"{key.upper()}_API_KEY",), (f"{key.upper()}_FREE_MODELS",), "", key, slot)


def _runtime_success(seat, rid, round_no, content="live result"):
    model = "deepseek-flash" if seat.key == "deepseek" else "gemini-3.8-flash"
    return {
        "status": "SUCCESS", "classification": "SUCCESS", "seat": seat.key, "name": seat.name,
        "model": model, "executed_model": model, "attempted_models": [model],
        "request_id": rid, "round": round_no,
        "runtime_execution_events": [{"execution_started": True, "status": "SUCCESS",
                                      "request_id": rid, "round": round_no, "provider": seat.key}],
        "content": content, "_provider_input_prompt": "runtime prompt",
        "_runtime_payload_attestation": ({"payload_json": '{"input":"runtime prompt"}', "payload_sha256": "x"}
                                         if seat.key == "gemini" else {}),
    }


def test_hotfix1642_prompt_excludes_bridge_id_key_and_value_for_gemini():
    b = main.SharedContextBridge(request_id="rid-1642", round_no=2, application_owned_test=True)
    b.seed_application_state("BRIDGE_RESULT", "CANARY", source="DeepSeek", source_seat=7)
    b.attest_source_execution(True, "APPLICATION_TEST_CONTROL")
    p = b.prompt_snapshot(_seat("gemini", "Gemini", 2))
    assert b.bridge_id not in p
    assert "BRIDGE_RESULT" not in p
    assert "CANARY" not in p


def test_hotfix1642_abort_turns_pending_into_terminal_state():
    b = main.SharedContextBridge(request_id="rid-abort", round_no=2, application_owned_test=True)
    b.seed_application_state("BRIDGE_RESULT", "CANARY", source="DeepSeek", source_seat=7)
    b.abort("SOURCE_EXECUTION_NOT_PROVEN")
    state = b.application_owned_state()
    assert state["committed"] is False
    assert state["barrier_open"] is False
    assert state["terminal_state"] == "ABORTED"
    assert all(t.get("commit_status") != "PENDING" for t in state["trace"])


def test_hotfix1642_existing_request_reconcile_preserves_identity():
    chat = {"conversation_id":"c","session_id":"s","conversation_record":{"conversation_id":"c","session_id":"s","messages":[],"requests":[],"rounds":[]}}
    a = canonical_upsert_request(chat, {"request_id":"r1","message_id":"m1","canonical_round_base":1})
    b = canonical_upsert_request(chat, {"request_id":"r1","message_id":"m1"})
    assert a["canonical_round_base"] == 1
    assert b["canonical_round_base"] == 1
    assert b.get("identity_conflict") is not True


def test_hotfix1642_live_mode_rejects_application_control_seed():
    b = main.SharedContextBridge(request_id="rid-live", round_no=1, strict_live_source=True)
    b.seed_application_state("BRIDGE_RESULT", "CONTROL", source="DeepSeek", source_seat=7)
    b.attest_source_execution(True, "LIVE_PROVIDER_RESULT")
    try:
        b.commit(_seat("gemini", "Gemini", 2))
    except RuntimeError:
        return
    raise AssertionError("application control seed was incorrectly accepted")


def test_hotfix1642_final_runtime_source_precedes_target(monkeypatch):
    ds, gem = _seat("deepseek","DeepSeek",7), _seat("gemini","Gemini",2)
    calls=[]
    def fake_call(seat, user_prompt, shared_context, round_no, local_fallback, credential, attachments, candidates, deadline, request_id):
        calls.append((seat.key, bool("BRIDGE SOURCE HANDOFF" in shared_context)))
        return _runtime_success(seat, request_id, round_no, "DEEPSEEK_LIVE_BRIDGE_VALUE" if seat.key=="deepseek" else "target response")
    monkeypatch.setattr(main,"get_seats",lambda:(ds,gem))
    monkeypatch.setattr(main,"call_seat",fake_call)
    chat={"conversation_id":"c","session_id":"s","messages":[],"conversation_record":{"messages":[],"requests":[],"rounds":[]}}
    out=main._run_round("FINAL RUNTIME CLOSURE TEST\nTRANSACTIONAL BRIDGE ISOLATION",chat,1,{"deepseek":"k","gemini":"k"},[],{"deepseek":("deepseek-flash",),"gemini":("gemini-3.8-flash",)},"m",None,"rid")
    by={x["seat"]:x for x in out}
    assert calls == [("deepseek",True),("gemini",False)]
    a=chat["bridge_runtime_evidence_store"]["rid"]
    assert a["source_execution_proven"] == "PASS"
    assert a["write_status"] == "PASS" and a["validate_status"] == "PASS"
    assert a["commit_status"] == "PASS" and a["barrier_status"] == "PASS"
    assert a["target_dispatch_status"] == "PASS" and a["target_response_status"] == "PASS"
    assert a["read_status"] == "PASS" and a["schema_validation_status"] == "PASS" and a["match_status"] == "PASS"
    assert a["runtime_sequence_valid"] == "PASS"
    assert [e["phase"] for e in a["runtime_sequence"]] == ["SOURCE_EXECUTION","WRITE","VALIDATE","COMMIT","BARRIER","TARGET_DISPATCH","TARGET_RESPONSE","READ","MATCH"]
    assert a["runtime_http_payload_attested"] == "YES"
    assert a["runtime_http_payload_contains_value"] == "NO"
    assert a["runtime_http_payload_contains_bridge_key"] == "NO"
    assert a["gemini_received_sanitized_representation_only"] == "PASS"
    assert a["terminal_state"] == "COMMITTED"
    assert "bridge_transaction_audit" not in by["gemini"]


def test_hotfix1642_final_runtime_source_not_executed_suppresses_target(monkeypatch):
    ds, gem = _seat("deepseek","DeepSeek",7), _seat("gemini","Gemini",2)
    calls=[]
    def fake_call(seat, *args, **kwargs):
        calls.append(seat.key)
        rid=kwargs.get("request_id") or args[-1]
        if seat.key=="deepseek":
            return {"status":"NOT_EXECUTED","classification":"NOT_EXECUTED","seat":"deepseek","name":"DeepSeek", "model":"","executed_model":"","attempted_models":[],"runtime_execution_events":[],"request_id":rid,"round":1,"content":""}
        raise AssertionError("Gemini must not dispatch")
    monkeypatch.setattr(main,"get_seats",lambda:(ds,gem))
    monkeypatch.setattr(main,"call_seat",fake_call)
    chat={"conversation_id":"c","session_id":"s","messages":[],"conversation_record":{"messages":[],"requests":[],"rounds":[]}}
    out=main._run_round("FINAL RUNTIME CLOSURE TEST\nTRANSACTIONAL BRIDGE ISOLATION",chat,1,{"deepseek":"k","gemini":"k"},[],{"deepseek":("deepseek-flash",),"gemini":("gemini-3.8-flash",)},"m",None,"rid")
    assert calls == ["deepseek"]
    by={x["seat"]:x for x in out}
    assert by["gemini"]["dispatch_decision"] == "DISPATCH_SUPPRESSED"
    state=chat["bridge_runtime_evidence_store"]["rid"]
    assert state["terminal_state"] == "ABORTED"
    assert state["commit_status"] == "FAIL"
    assert "_bridge_application_state" not in by["gemini"]


def test_hotfix1642_canonical_identity_counts_only_user_messages():
    record={"messages":[{"message_id":"m1","role":"user"},{"message_id":"a1","role":"assistant"},{"message_id":"a2","role":"assistant"}],"requests":[{"request_id":"r1"},{"request_id":"r2"}],"rounds":[{"round_id":"q1"},{"round_id":"q2"}]}
    counts=canonical_identity_counts(record)
    assert counts == {"canonical_message_count":1,"canonical_request_count":2,"canonical_round_count":2}
