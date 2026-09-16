from unittest.mock import patch
import main
import providers

def test_version_contract():
    assert providers.VERSION == "V22.1-HOTFIX87-PRODUCTION-HARDENED"

def test_deepseek_alias_attestation():
    ds = providers.BUILTIN_SEATS[-1]
    with patch("providers.call_official", return_value={"text":"OK", "provider_reported_model":"deepseek-v4-flash-0731"}):
        r=providers.call_seat(ds,"x","",1,False,"TEST",[],("deepseek-v4-flash",),request_id="rid87")
    assert r["status"]=="SUCCESS"
    assert r["provider_reported_model"]=="deepseek-v4-flash-0731"
    assert r["attempt_summaries"][-1]["final_result"]=="SUCCESS"

def test_attempt_trace_contains_required_safe_fields():
    seat=providers.BUILTIN_SEATS[1]
    with patch("providers.call_official", side_effect=[providers.ProviderError("temporary",503,"provider_server"), {"text":"OK","provider_reported_model":"m2"}]):
        r=providers.call_seat(seat,"x","",2,False,"SECRET-KEY",[],("m1","m2"),request_id="rid87")
    assert r["status"]=="SUCCESS"
    assert r["attempted_models"]==["m1","m2"]
    assert r["attempt_summaries"][0]["status_code"]==503
    assert r["attempt_summaries"][0]["classification"]=="API_ERROR"
    assert r["attempt_summaries"][0]["retryable"] is True
    assert r["attempt_summaries"][0]["request_id"]=="rid87"
    assert r["attempt_summaries"][0]["round"]==2
    assert r["attempt_summaries"][-1]["final_result"]=="SUCCESS"
    assert "SECRET-KEY" not in repr(r["attempt_summaries"])

def test_bridge_dependency_order_deepseek_then_gemini(monkeypatch):
    seen={}; seats=main.get_seats()
    def fake(seat,user_prompt,shared_context,round_no,local_fallback,credential,attachments=None,model_candidates=None,deadline=None,request_id=""):
        seen[seat.key]=shared_context; model=(model_candidates or ("m",))[0]
        content="BRIDGE_WRITE: BRIDGE_RESULT = DEEPSEEK-7-GENERATED-87" if seat.key=="deepseek" else "OK"
        return {"seat":seat.key,"name":seat.name,"label":seat.label,"status":"SUCCESS","mode":"official","model":model,"executed_model":model,"provider_reported_model":model,"content":content,"error":None,"latency":.001,"attempted_models":[model],"attempt_diagnostics":[],"attempt_summaries":[],"official_authenticated":True,"request_id":request_id,"round":round_no}
    monkeypatch.setattr(main,"call_seat",fake)
    c={s.key:"TEST" for s in seats}; m={s.key:("m",) for s in seats}; chat={"messages":[],"request_ids":[],"request_records":[],"history_identity_ledger":[],"result_keys":[]}
    out=main._run_round("bridge",chat,1,c,[],m,"u",None,"rid87")
    assert "Source seat: 7" in seen["gemini"]
    assert "Key: BRIDGE_RESULT" in seen["gemini"]
    assert "Value: DEEPSEEK-7-GENERATED-87" in seen["gemini"]
    assert [r["seat"] for r in out]==[s.key for s in seats]


def test_success_attempt_telemetry_keeps_success_classification_and_latency():
    seat = providers.BUILTIN_SEATS[1]
    with patch("providers.call_official", return_value={"text":"OK", "provider_reported_model":"m1"}):
        r = providers.call_seat(seat, "x", "", 1, False, "SECRET-KEY", [], ("m1",), request_id="rid-success")
    summary = r["attempt_summaries"][-1]
    assert summary["classification"] == "SUCCESS"
    assert summary["final_result"] == "SUCCESS"
    assert "latency" in summary
    assert summary["request_id"] == "rid-success"


def test_bridge_schema_rejects_malformed_provider_output_and_isolates_next_provider(monkeypatch):
    seen = {}
    seats = main.get_seats()

    def fake_call_seat(seat, user_prompt, shared_context, round_no, local_fallback, credential, attachments=None, model_candidates=None, deadline=None, request_id=""):
        seen[seat.key] = shared_context
        model = (model_candidates or ("m",))[0]
        if seat.key == "deepseek":
            return {"seat": "wrong-seat", "name": seat.name, "status": "SUCCESS", "model": model, "executed_model": model, "content": "BRIDGE_WRITE: BRIDGE_RESULT = BAD", "request_id": request_id, "round": round_no}
        return {"seat": seat.key, "name": seat.name, "label": seat.label, "status": "SUCCESS", "mode": "official", "model": model, "executed_model": model, "provider_reported_model": model, "content": "OK", "error": None, "latency": .001, "attempted_models": [model], "attempt_diagnostics": [], "attempt_summaries": [], "official_authenticated": True, "request_id": request_id, "round": round_no}

    monkeypatch.setattr(main, "call_seat", fake_call_seat)
    credentials = {s.key: "TEST" for s in seats}
    candidates = {s.key: ("m",) for s in seats}
    chat = {"messages": [], "request_ids": [], "request_records": [], "history_identity_ledger": [], "result_keys": []}
    results = main._run_round("x", chat, 1, credentials, [], candidates, "u", None, "rid-schema")
    deepseek = next(r for r in results if r["seat"] == "deepseek")
    assert deepseek["status"] == "FAILED"
    assert deepseek["bridge_validation"]["valid"] is False
    assert "wrong-seat" in deepseek["bridge_validation"]["reason"] or deepseek["bridge_validation"]["reason"] == "seat_identity_mismatch"
    # Gemini must continue independently and must not receive the malformed bridge write.
    assert "Key: BRIDGE_RESULT" not in seen.get("gemini", "")


def test_provider_failure_isolation_continues_other_seats(monkeypatch):
    seats = main.get_seats()
    called = []

    def fake_call_seat(seat, user_prompt, shared_context, round_no, local_fallback, credential, attachments=None, model_candidates=None, deadline=None, request_id=""):
        called.append(seat.key)
        model = (model_candidates or ("m",))[0]
        if seat.key == "claude":
            return {"seat": seat.key, "name": seat.name, "label": seat.label, "status": "FAILED", "mode": "official", "model": model, "executed_model": model, "content": "", "error": "HTTP 401; class=http_401_authentication_failed", "classification": "AUTHENTICATION_ERROR", "latency": .001, "attempted_models": [model], "attempt_diagnostics": [{"attempt":1,"model":model,"status_code":401,"classification":"AUTHENTICATION_ERROR","retryable":False,"latency":.001,"request_id":request_id,"round":round_no,"final_result":"FAILED"}], "attempt_summaries": [], "official_authenticated": False, "request_id":request_id, "round":round_no}
        return {"seat": seat.key, "name": seat.name, "label": seat.label, "status": "SUCCESS", "mode": "official", "model": model, "executed_model": model, "provider_reported_model": model, "content": "OK", "error": None, "latency": .001, "attempted_models": [model], "attempt_diagnostics": [], "attempt_summaries": [], "official_authenticated": True, "request_id": request_id, "round": round_no}

    monkeypatch.setattr(main, "call_seat", fake_call_seat)
    credentials = {s.key: "TEST" for s in seats}
    candidates = {s.key: ("m",) for s in seats}
    chat = {"messages": [], "request_ids": [], "request_records": [], "history_identity_ledger": [], "result_keys": []}
    results = main._run_round("x", chat, 1, credentials, [], candidates, "u", None, "rid-isolation")
    assert "claude" in called and "grok" in called and "deepseek" in called
    assert next(r for r in results if r["seat"] == "grok")["status"] == "SUCCESS"
    assert next(r for r in results if r["seat"] == "deepseek")["status"] == "SUCCESS"
