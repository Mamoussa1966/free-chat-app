import providers
from unittest.mock import patch


def test_gemini_uses_dedicated_interactive_timeout(monkeypatch):
    seat = next(s for s in providers.get_seats() if s.key == "gemini")
    seen = {}

    def fake_call_official(seat, prompt, model, credential, timeout, attachments=None, deadline=None):
        seen["timeout"] = timeout
        return "FAST_OK"

    monkeypatch.setattr(providers, "call_official", fake_call_official)
    monkeypatch.setattr(providers, "GEMINI_REQUEST_TIMEOUT", 12)
    result = providers.call_seat(seat, "hello", "", 1, False, "KEY", [], ("model-A",), None)
    assert result["status"] == "SUCCESS"
    assert seen["timeout"] == 12


def test_gemini_http_post_disables_extra_adapter_retry(monkeypatch):
    calls = []

    class Response:
        status_code = 500
        text = "temporary"
        headers = {}
        def json(self):
            return {"error": "temporary"}

    def fake_post(*args, **kwargs):
        calls.append(1)
        return Response()

    monkeypatch.setattr(providers.requests, "post", fake_post)
    try:
        providers._post(
            "https://generativelanguage.googleapis.com/v1beta/models/model-A:generateContent",
            {}, {}, 5
        )
    except providers.ProviderError:
        pass
    assert len(calls) == 1
