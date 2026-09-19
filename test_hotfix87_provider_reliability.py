from unittest.mock import patch

import main
import providers


def test_attempt_telemetry_contains_safe_required_fields_and_cascade_action():
    seat = providers.BUILTIN_SEATS[1]
    with patch("providers.call_official", side_effect=[
        providers.ProviderError("bad key", 401, "http_401_authentication_failed")
    ]):
        result = providers.call_seat(seat, "x", "", 1, False, "SECRET", [], ("m1",), request_id="RID-87")
    assert result["status"] == "FAILED"
    d = result["attempt_telemetry"][0]
    assert d["provider"] == "Gemini"
    assert d["attempt"] == 1
    assert d["model"] == "m1"
    assert d["status_code"] == 401
    assert d["classification"] == "AUTHENTICATION_ERROR"
    assert d["retryable"] is False
    assert d["execution_time"] >= 0
    assert d["request_id"] == "RID-87"
    assert d["round"] == 1
    assert d["final_result"] == "FAILED"
    assert d["cascade_action"] == "CASCADE_STOP"
    assert "SECRET" not in repr(result["attempt_telemetry"])


def test_provider_output_schema_gate_rejects_empty_output():
    seat = providers.BUILTIN_SEATS[1]
    with patch("providers.call_official", return_value={"text": "", "provider_reported_model": "m1"}):
        result = providers.call_seat(seat, "x", "", 1, False, "KEY", [], ("m1",), request_id="RID-SCHEMA")
    assert result["status"] == "FAILED"
    assert result["attempt_summaries"][-1]["classification"] == "API_ERROR"


def test_bridge_does_not_accept_unvalidated_or_malformed_provider_output():
    bridge = main.SharedContextBridge()
    seat = next(s for s in main.get_seats() if s.key == "deepseek")
    bridge.append_agent_output(seat, {"status": "SUCCESS", "seat": "deepseek", "content": "", "model": "m", "executed_model": "m"})
    assert "BRIDGE WRITE RECORD" not in bridge.snapshot()


def test_provider_isolation_uses_only_the_given_seat_credential():
    claude = next(s for s in providers.get_seats() if s.key == "claude")
    with patch("providers.call_official", side_effect=providers.ProviderError("auth", 401, "http_401_authentication_failed")) as mocked:
        providers.call_seat(claude, "x", "", 1, False, "CLAUDE-ONLY", [], ("claude-model",), request_id="RID-ISO")
    assert mocked.call_count == 1
    args = mocked.call_args.args
    assert "CLAUDE-ONLY" in args
    assert "GEMINI" not in repr(args)
