from unittest.mock import patch

import main
import providers


def test_timeout_is_internal_but_never_rendered_as_public_no_response(monkeypatch):
    seat = next(s for s in providers.get_seats() if s.key == "gemini")

    def fake_call_official(*args, **kwargs):
        raise providers.ProviderError("transport deadline", error_class="timeout")

    with patch("providers.call_official", side_effect=fake_call_official):
        result = providers.call_seat(
            seat, "hello", "", 1, False, "KEY", [],
            ("m1",), request_id="public-no-response-1"
        )

    # Transport layer keeps the truthful internal taxonomy.
    assert result["classification"] == "TIMEOUT"

    public = main._public_result(result)
    assert public["classification"] == main.PUBLIC_NO_RESPONSE
    assert public["attempt_summaries"][0]["classification"] == main.PUBLIC_NO_RESPONSE


def test_public_classifier_maps_timeout_to_no_response():
    result = {
        "status": "FAILED",
        "classification": "TIMEOUT",
        "attempt_summaries": [{"classification": "TIMEOUT", "model": "m1"}],
    }
    assert main._result_error_classification(result) == main.PUBLIC_NO_RESPONSE


def test_public_timeout_result_becomes_neutral_no_response_status():
    seat = next(s for s in providers.get_seats() if s.key == "gemini")

    def fake_call_official(*args, **kwargs):
        raise providers.ProviderError("transport deadline", error_class="timeout")

    with patch("providers.call_official", side_effect=fake_call_official):
        result = providers.call_seat(
            seat, "hello", "", 1, False, "KEY", [],
            ("m1",), request_id="public-no-response-status-1"
        )

    public = main._public_result(result)
    assert public["status"] == main.PUBLIC_NO_RESPONSE
    assert public["classification"] == main.PUBLIC_NO_RESPONSE
    assert "TIMEOUT" not in str(public)


def test_public_timeout_does_not_render_failed_timeout_expander(monkeypatch):
    calls = []
    monkeypatch.setattr(main.st, "warning", lambda text: calls.append(("warning", text)))
    monkeypatch.setattr(main.st, "expander", lambda *a, **k: (_ for _ in ()).throw(AssertionError("timeout must not render expander")))
    main._render_result_line({
        "status": main.PUBLIC_NO_RESPONSE,
        "label": "🔑 Gemini",
        "classification": main.PUBLIC_NO_RESPONSE,
    })
    assert calls
    assert "TIMEOUT" not in calls[0][1]
