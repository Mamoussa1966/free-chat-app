from pathlib import Path
from production_core import RequestLifecycle, RequestState, TransactionBridgeGuard
from unittest.mock import patch
from providers import SEATS, ProviderError, call_seat

def test_bridge_read_requires_barrier():
    b=TransactionBridgeGuard(); b.stage("deepseek","gemini","BRIDGE_RESULT"); b.commit()
    try: b.read("gemini")
    except RuntimeError: pass
    else: raise AssertionError("READ before BARRIER must fail")
    b.barrier(); b.read("gemini"); assert b.state.value == "BARRIER_OPEN"

def test_executed_cascade_position_matches_actual_http_attempt():
    gem=next(s for s in SEATS if s.key=="gemini"); seen=[]
    def fake(*a,**k):
        seen.append(a[2])
        if len(seen)<3: raise ProviderError("unavailable", error_class="model_unavailable", status_code=404)
        return "ok"
    with patch("providers.call_official", side_effect=fake):
        r=call_seat(gem,"x","",1,False,"key",[],("m1","m2","m3"),None,"RID114")
    assert seen==["m1","m2","m3"]
    assert r["executed_model"]=="m3"
    assert r["cascade_position"]==3==r["executed_cascade_position"]
    assert r["attempted_models"]==seen

def test_failed_provider_never_returns_success():
    gem=next(s for s in SEATS if s.key=="gemini")
    with patch("providers.call_official", side_effect=ProviderError("down", error_class="api_error", status_code=500)):
        r=call_seat(gem,"x","",1,False,"key",[],("m1",),None,"RID114F")
    assert r["status"] != "SUCCESS"
    assert r["classification"] == "API_ERROR"

def test_lifecycle_has_production_gate_events():
    life=RequestLifecycle.begin("RID114L")
    life.record("REQUEST_START"); life.record("ROUTING"); life.record("PROVIDER_EXECUTION"); life.record("RESPONSE_VALIDATION"); life.record("REQUEST_COMMIT")
    life.start_round(1); life.finish_round(1,1,1); life.finish(True)
    kinds=[e.event_type for e in life.audit]
    for x in ("REQUEST_START","ROUTING","PROVIDER_EXECUTION","RESPONSE_VALIDATION","REQUEST_COMMIT"):
        assert x in kinds
    assert life.state is RequestState.COMPLETED

def test_version():
    assert Path("VERSION.txt").read_text().strip()=="V22.1-HOTFIX120.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE"
