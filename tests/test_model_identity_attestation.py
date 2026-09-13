import providers


def _deepseek():
    return next(s for s in providers.SEATS if s.key == "deepseek")


def test_model_identity_is_end_to_end_attested(monkeypatch):
    seat = _deepseek()
    requested = "deepseek-v4-flash"
    captured = {}

    def fake_post(endpoint, headers, payload, timeout, deadline):
        captured["request_model"] = payload["model"]
        return {
            "id": "test-response-id",
            "model": requested,
            "choices": [{"message": {"role": "assistant", "content": "IDENTITY_OK"}}],
        }

    monkeypatch.setattr(providers, "_post", fake_post)
    result = providers.call_seat(
        seat=seat, user_prompt="identity test", shared_context="", round_no=1,
        local_fallback=False, credential="TEST_KEY", attachments=[],
        model_candidates=(requested,), request_id="identity-test-001",
    )

    assert result["status"] == "SUCCESS"
    assert requested == captured["request_model"]
    assert captured["request_model"] == result["provider_reported_model"]
    assert result["provider_reported_model"] == result["executed_model"]
    assert result["executed_model"] == result["model"]


def test_model_identity_mismatch_fails_closed(monkeypatch):
    seat = _deepseek()

    def fake_post(endpoint, headers, payload, timeout, deadline):
        return {
            "id": "test-response-id",
            "model": "different-model",
            "choices": [{"message": {"role": "assistant", "content": "SHOULD_NOT_BE_ACCEPTED"}}],
        }

    monkeypatch.setattr(providers, "_post", fake_post)
    result = providers.call_seat(
        seat=seat, user_prompt="identity mismatch test", shared_context="", round_no=1,
        local_fallback=False, credential="TEST_KEY", attachments=[],
        model_candidates=("deepseek-v4-flash",), request_id="identity-test-002",
    )

    assert result["status"] != "SUCCESS"
    assert result["attempt_diagnostics"][0]["classification"] == "API_ERROR"
    assert result["attempted_models"] == ["deepseek-v4-flash"]


def test_missing_provider_model_identity_fails_closed(monkeypatch):
    seat = _deepseek()

    def fake_post(endpoint, headers, payload, timeout, deadline):
        return {
            "id": "test-response-id",
            "choices": [{"message": {"role": "assistant", "content": "NO_ATTESTATION"}}],
        }

    monkeypatch.setattr(providers, "_post", fake_post)
    result = providers.call_seat(
        seat=seat, user_prompt="missing identity test", shared_context="", round_no=1,
        local_fallback=False, credential="TEST_KEY", attachments=[],
        model_candidates=("deepseek-v4-flash",), request_id="identity-test-003",
    )

    assert result["status"] != "SUCCESS"
    assert result["attempt_diagnostics"][0]["classification"] == "API_ERROR"
