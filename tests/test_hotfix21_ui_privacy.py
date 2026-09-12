from pathlib import Path
import inspect
import main


def test_history_uses_compact_attempt_summaries_field():
    source = Path(__file__).resolve().parents[1].joinpath('main.py').read_text(encoding='utf-8')
    assert '"attempt_summaries": _history_attempt_summaries' in source
    assert '"attempt_diagnostics": _history_attempt_summaries' not in source


def test_temporary_attempt_renderer_uses_unique_dom_id_and_60_second_ttl():
    source = inspect.getsource(main._render_temporary_attempt_diagnostic)
    assert 'uuid.uuid4().hex' in source
    assert 'attempt-error-' in source
    assert 'ERROR_DISPLAY_TTL_SECONDS' in inspect.getsource(main._attempt_display_remaining)
    assert main.ERROR_DISPLAY_TTL_SECONDS == 60


def test_persisted_results_strip_raw_provider_diagnostics():
    raw = "HTTP 429 secret=DO_NOT_PERSIST provider JSON https://example.invalid/private"
    public = main._public_result({
        "status": "SUCCESS",
        "model": "gemini-3.8-flash",
        "executed_model": "gemini-3.8-flash",
        "content": "ok",
        "error": raw,
        "attempt_diagnostics": [{
            "attempt": 1, "model": "gemini-a", "status_code": 429,
            "classification": "QUOTA_EXCEEDED", "error": raw,
            "_display_created_at": 1000.0,
        }],
    })
    assert "attempt_diagnostics" not in public
    assert "error" not in public
    assert public["attempt_summaries"][0]["classification"] == "QUOTA_EXCEEDED"
    assert "DO_NOT_PERSIST" not in str(public)
    assert "example.invalid" not in str(public)
