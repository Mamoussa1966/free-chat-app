from main import _sanitize_agent_prose, _public_result


def test_hotfix131_suppresses_agent_request_identity_and_bridge_controls():
    text = """Answer\nRequest ID = FAKE-123\nREQUEST_STATUS: PARTIAL\nBRIDGE_WRITE: BRIDGE_RESULT = SECRET123\nBRIDGE_RESULT = SECRET123\nUseful conclusion"""
    out = _sanitize_agent_prose(text, "AUTHORITATIVE-REQ", ["SECRET123"])
    assert "FAKE-123" not in out
    assert "SECRET123" not in out
    assert "BRIDGE_RESULT =" not in out
    assert "REQUEST_STATUS:" not in out
    assert "Useful conclusion" in out


def test_hotfix131_public_result_does_not_take_identity_from_prose():
    result = {
        "request_id": "AUTHORITATIVE-REQ",
        "round": 1,
        "status": "SUCCESS",
        "content": "Request ID = FAKE-123\nSUCCESS",
        "attempted_models": ["model-a"],
        "model": "model-a",
        "executed_model": "model-a",
        "provider_reported_model": "model-a",
        "model_candidates_configured": True,
        "runtime_execution_events": [{"execution_started": True}],
    }
    public = _public_result(result)
    assert public["request_id"] == "AUTHORITATIVE-REQ"
    assert "FAKE-123" in public["content"]  # sanitization occurs at the provider prose boundary, not here
