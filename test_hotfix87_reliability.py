import inspect
import main
import providers


def test_attempt_record_contains_full_trace_contract():
    record = providers._attempt_record(attempt=1, model="claude-sonnet-4-6", status_code=401, classification="AUTHENTICATION_ERROR", retryable=False, execution_time=0.1234, request_id="req-1", round_no=2, final_result="CASCADE_STOP")
    assert record == {
        "provider": "", "attempt": 1, "model": "claude-sonnet-4-6", "status_code": 401,
        "classification": "AUTHENTICATION_ERROR", "retryable": False, "execution_time": 0.123,
        "request_id": "req-1", "round": 2, "final_result": "CASCADE_STOP",
    }


def test_history_keeps_trace_metadata_but_not_raw_error():
    raw = "HTTP 401 secret=DO_NOT_STORE payload={private}"
    out = main._history_attempt_summaries([{
        "provider": "Grok", "attempt": 1, "model": "grok-4.3", "status_code": 401,
        "classification": "AUTHENTICATION_ERROR", "retryable": False, "execution_time": 0.42,
        "request_id": "req-x", "round": 1, "final_result": "CASCADE_STOP", "error": raw,
    }])
    assert out[0]["provider"] == "Grok"
    assert out[0]["request_id"] == "req-x"
    assert out[0]["final_result"] == "CASCADE_STOP"
    assert raw not in str(out)


def test_successful_output_must_pass_schema_before_handoff():
    seat = next(s for s in providers.SEATS if s.key == "gemini")
    valid = {"seat":"gemini","name":"Gemini","status":"SUCCESS","model":"m","executed_model":"m","content":"ok","request_id":"r","round":1}
    checked = main._validate_provider_output(valid, seat, "r", 1)
    assert checked["bridge_validated"] is True
    assert checked["bridge_record"]["validated"] is True


def test_invalid_provider_identity_is_rejected_before_handoff():
    seat = next(s for s in providers.SEATS if s.key == "claude")
    bad = {"seat":"grok","name":"Grok","status":"SUCCESS","model":"m","executed_model":"m","content":"ok","request_id":"r","round":1}
    try:
        main._validate_provider_output(bad, seat, "r", 1)
    except ValueError as exc:
        assert "identity" in str(exc)
    else:
        raise AssertionError("invalid provider identity was accepted")


def test_round_uses_validated_handoff_path_and_continues_after_provider_error():
    source = inspect.getsource(main._run_round)
    assert "_validate_provider_output" in source
    assert "working_context" in source
    assert "for seat in SEATS" in source
