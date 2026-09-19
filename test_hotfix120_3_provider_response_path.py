from types import SimpleNamespace

import main
import providers


class _Response:
    status_code = 200
    headers = {}
    text = "{}"

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": "Gemini OK"}]}}]}


def test_gemini_official_response_envelope_has_no_unbound_model(monkeypatch):
    monkeypatch.setattr(providers.requests, "post", lambda *a, **k: _Response())
    seat = next(s for s in providers.get_seats() if s.key == "gemini")
    result = providers.call_official(seat, "hello", "gemini-3.8-flash", "test-key")
    assert result["text"] == "Gemini OK"
    assert result["provider_reported_model"] == "gemini-3.8-flash"


def test_live_cascade_telemetry_renderer_exists_and_does_not_execute_requests(monkeypatch):
    rendered = []
    monkeypatch.setattr(main.st, "caption", lambda value: rendered.append(value))
    main._render_live_cascade_telemetry({
        "name": "DeepSeek",
        "request_id": "REQ-1",
        "round": 1,
        "attempt_telemetry": [{
            "attempt": 1, "model": "deepseek-flash",
            "classification": "MODEL_UNAVAILABLE",
            "cascade_action": "CASCADE_CONTINUE",
            "request_id": "REQ-1", "round": 1,
        }]
    })
    assert len(rendered) == 1
    assert "deepseek-flash" in rendered[0]
    assert "MODEL_UNAVAILABLE" in rendered[0]
    assert "CASCADE_CONTINUE" in rendered[0]
    assert "REQ-1" in rendered[0]
