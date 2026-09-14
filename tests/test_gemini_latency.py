import providers


def _gemini():
    return next(s for s in providers.get_seats() if s.key == "gemini")


def test_gemini_uses_latency_cap_and_no_hidden_http_retry(monkeypatch):
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
        model_candidates=("gemini-test-model",), request_id="gemini-latency-001",
    )

    assert result["status"] == "SUCCESS"
    assert seen["timeout"] == min(providers.REQUEST_TIMEOUT, providers.GEMINI_REQUEST_TIMEOUT_SECONDS)
    assert seen["retries"] == providers.GEMINI_RETRIES == 0
    assert result["successful_attempt_latency"] >= 0
    assert result["effective_timeout"] == seen["timeout"]


def test_failed_attempts_record_latency_and_timeout(monkeypatch):
    seat = _gemini()

    def fake_post(endpoint, headers, payload, timeout, deadline, retries=None):
        raise providers.ProviderError("timeout", error_class="timeout")

    monkeypatch.setattr(providers, "_post", fake_post)
    result = providers.call_seat(
        seat=seat, user_prompt="hello", shared_context="", round_no=1,
        local_fallback=False, credential="TEST_KEY", attachments=[],
        model_candidates=("gemini-test-model",), request_id="gemini-latency-002",
    )

    assert result["status"] == "FAILED"
    detail = result["attempt_diagnostics"][0]
    assert detail["latency"] >= 0
    assert detail["timeout_seconds"] == min(providers.REQUEST_TIMEOUT, providers.GEMINI_REQUEST_TIMEOUT_SECONDS)
