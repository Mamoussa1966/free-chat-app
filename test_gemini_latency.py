import providers


def _gemini():
    return next(s for s in providers.get_seats() if s.key == "gemini")


def test_gemini_has_no_artificial_latency_cap_or_hidden_retry(monkeypatch):
    seat = _gemini()
    seen = {}

    def fake_post(endpoint, headers, payload, timeout, deadline, retries=None):
        seen["timeout"] = timeout
        seen["retries"] = retries
        return {
            "candidates": [{"content": {"parts": [{"text": "FAST_OK"}]}}],
        }

    monkeypatch.setattr(providers, "_post", fake_post)
    result = providers.call_seat(
        seat=seat, user_prompt="hello", shared_context="", round_no=1,
        local_fallback=False, credential="TEST_KEY", attachments=[],
        model_candidates=("gemini-test-model",), request_id="gemini-unlimited-001",
    )

    assert result["status"] == "SUCCESS"
    assert seen["timeout"] is None
    assert seen["retries"] == providers.GEMINI_RETRIES == 0
    assert result["successful_attempt_latency"] >= 0
    assert result["effective_timeout"] is None


def test_failed_attempts_record_latency_without_timeout_budget(monkeypatch):
    seat = _gemini()

    def fake_post(endpoint, headers, payload, timeout, deadline, retries=None):
        raise providers.ProviderError("timeout", error_class="timeout")

    monkeypatch.setattr(providers, "_post", fake_post)
    result = providers.call_seat(
        seat=seat, user_prompt="hello", shared_context="", round_no=1,
        local_fallback=False, credential="TEST_KEY", attachments=[],
        model_candidates=("gemini-test-model",), request_id="gemini-unlimited-002",
    )

    assert result["status"] == "FAILED"
    detail = result["attempt_diagnostics"][0]
    assert detail["latency"] >= 0
    assert detail["timeout_seconds"] is None
