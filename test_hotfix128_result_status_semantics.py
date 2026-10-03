from main import _hotfix128_result_semantics
from providers import _result, Seat

def _seat():
    return Seat("gemini", "Gemini", "Gemini", ("GEMINI_API_KEY",), ("GEMINI_FREE_MODELS",), "", "gemini", 2)

def test_no_attempted_models_never_becomes_api_error():
    r = _hotfix128_result_semantics({"status":"FAILED","classification":"API_ERROR","attempted_models":[],"model_candidates_configured":True})
    assert r["status"] == "NOT_EXECUTED"
    assert r["classification"] == "NOT_EXECUTED"

def test_worker_dispatch_rejection_is_not_provider_error():
    r = _hotfix128_result_semantics({"status":"DISPATCH_REJECTED","classification":"API_ERROR","attempted_models":[],"model_candidates_configured":True})
    assert r["status"] == "DISPATCH_REJECTED"
    assert r["classification"] == "DISPATCH_REJECTED"

def test_zero_models_is_not_api_failure():
    r = _hotfix128_result_semantics({"status":"NO_FREE_MODEL_CONFIGURED","classification":"MODEL_UNAVAILABLE","attempted_models":[],"model_candidates_configured":False})
    assert r["status"] == "NOT_CONFIGURED"
    assert r["classification"] == "NOT_CONFIGURED"

def test_provider_credential_missing_is_not_api_attempt():
    s = _seat()
    r = _result(s, "NOT_CONFIGURED", "", "", "class=not_configured; No official credential configured.", 0.0, [], request_id="r", round_no=1)
    assert r["status"] == "NOT_CONFIGURED"
    assert r["classification"] == "NOT_CONFIGURED"
    assert r["runtime_execution_events"] == []

def test_success_requires_actual_attempt_model():
    r = _hotfix128_result_semantics({"status":"SUCCESS","classification":"SUCCESS","attempted_models":[],"model_candidates_configured":True})
    assert r["status"] == "NOT_EXECUTED"
    assert r["classification"] == "NOT_EXECUTED"
