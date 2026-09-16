from unittest.mock import patch
import main
import providers


def test_hotfix87_bridge_order_places_deepseek_before_gemini(monkeypatch):
    order=[]
    seats=main.get_seats()
    def fake_call(seat, user_prompt, shared_context, round_no, local_fallback, credential, attachments=None, model_candidates=None, deadline=None, request_id=""):
        order.append(seat.key)
        model=(model_candidates or ("test-model",))[0]
        content="BRIDGE_WRITE: BRIDGE_RESULT = GENERATED-BY-DEEPSEEK" if seat.key=="deepseek" else ("GENERATED-BY-DEEPSEEK" if seat.key=="gemini" else "OK")
        if seat.key=="gemini":
            assert "Key: BRIDGE_RESULT" in shared_context
            assert "Value: GENERATED-BY-DEEPSEEK" in shared_context
        return {"seat":seat.key,"name":seat.name,"label":seat.label,"status":"SUCCESS","mode":"official","model":model,"executed_model":model,"provider_reported_model":model,"content":content,"error":None,"latency":0.001,"attempted_models":[model],"attempt_diagnostics":[],"attempt_summaries":[],"official_authenticated":True,"request_id":request_id,"round":round_no}
    monkeypatch.setattr(main,"call_seat",fake_call)
    credentials={s.key:"TEST" for s in seats}
    candidates={s.key:("test-model",) for s in seats}
    chat={"messages":[],"request_ids":[],"request_records":[],"history_identity_ledger":[],"result_keys":[]}
    results=main._run_round("bridge",chat,1,credentials,[],candidates,"u87",None,"r87")
    assert order[:2]==["deepseek","gemini"]
    assert [r["seat"] for r in results]==[s.key for s in seats]


def test_hotfix87_attempt_summary_contains_required_reliability_fields():
    result=providers._result(providers.get_seats()[0],"FAILED","m","","class=AUTHENTICATION_ERROR; safe",0.0,["m"],request_id="req-87",round_no=2,attempt_diagnostics=[{"attempt":1,"model":"m","status_code":401,"classification":"AUTHENTICATION_ERROR","retryable":False,"latency":0.12,"request_id":"req-87","round":2,"provider":"openai","final_result":"FAILED"}])
    row=result["attempt_summaries"][0]
    assert {"attempt","model","status_code","classification","retryable","latency","request_id","round","provider","final_result"} <= set(row)


def test_hotfix87_deepseek_versioned_identity_alias_remains_valid():
    assert providers._deepseek_model_identity_matches("deepseek-v4-flash","deepseek-v4-flash-0731")
