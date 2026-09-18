from pathlib import Path
import main
from providers import _prompt


def _result(seat, content, model="test-model", request_id="rid112", round_no=1):
    return {
        "status": "SUCCESS",
        "seat": seat.key,
        "model": model,
        "executed_model": model,
        "content": content,
        "round": round_no,
        "request_id": request_id,
    }


def test_hotfix113_prompt_boundary_redacts_value_even_when_embedded_in_prose():
    ds = next(s for s in main.get_seats() if s.key == "deepseek")
    gem = next(s for s in main.get_seats() if s.key == "gemini")
    bridge = main.SharedContextBridge(request_id="rid112-a", round_no=1)
    value = "DS112-SECRET-7X9Q"
    bridge.append_agent_output(ds, _result(ds, f"BRIDGE_WRITE: BRIDGE_RESULT = {value}"))
    bridge._entries.append(f"Provider prose accidentally repeated {value} outside the protocol record.")
    prompt = bridge.prompt_snapshot(gem)
    assert value not in prompt
    assert "BRIDGE READ AVAILABLE (VALUE NOT IN PROMPT)" in prompt


def test_hotfix113_actual_provider_prompt_is_captured_and_redacted():
    ds = next(s for s in main.get_seats() if s.key == "deepseek")
    gem = next(s for s in main.get_seats() if s.key == "gemini")
    bridge = main.SharedContextBridge(request_id="rid112-b", round_no=1)
    value = "DS112-ACTUAL-PROMPT-LEAK-CANARY"
    bridge.append_agent_output(ds, _result(ds, f"BRIDGE_WRITE: BRIDGE_RESULT = {value}"))
    bridge.commit(gem)
    bridge.barrier()
    raw_user = f"The user repeats {value} here."
    safe_user = bridge.sanitize_user_prompt(raw_user)
    provider_prompt = _prompt(safe_user, bridge.prompt_snapshot(gem), 1, gem, "gemini-3.8-flash")
    bridge.record_provider_input(gem, provider_prompt)
    audit = bridge.transaction_audit(user_prompt=raw_user)
    assert value in raw_user
    assert value not in safe_user
    assert value not in provider_prompt
    assert audit["USER_PROMPT_CONTAINS_VALUE"] == "YES"
    assert audit["GEMINI_INPUT_PROMPT_CONTAINS_VALUE"] == "NO"
    assert audit["BRIDGE_STATE_CONTAINS_VALUE"] == "YES"


def test_hotfix113_release_identity_is_canonical():
    version = Path("VERSION.txt").read_text(encoding="utf-8").strip()
    assert version == "V22.1-HOTFIX117-PRODUCTION-HARDENED"
    assert main.APP_VERSION == version


def test_hotfix113_application_owned_read_closes_gap_when_target_omits_control_record():
    ds = next(s for s in main.get_seats() if s.key == "deepseek")
    gem = next(s for s in main.get_seats() if s.key == "gemini")
    bridge = main.SharedContextBridge(request_id="rid112-c", round_no=1)
    value = "DS112-READ-GAP-CLOSED"
    bridge.append_agent_output(ds, _result(ds, f"BRIDGE_WRITE: BRIDGE_RESULT = {value}"))
    bridge.commit(gem)
    bridge.barrier()
    # Gemini's real HTTP response is allowed to omit the optional control line.
    resolution = bridge.consume_read_requests(gem, _result(gem, "I answered the user normally."))
    assert resolution["status"] == "RESOLVED"
    assert resolution["value"] == value
    audit = bridge.transaction_audit(user_prompt="HOTFIX117 bridge isolation test")
    assert audit["WRITE"] == "PASS"
    assert audit["VALIDATE"] == "PASS"
    assert audit["COMMIT"] == "PASS"
    assert audit["BARRIER"] == "PASS"
    assert audit["READ"] == "PASS"
    assert audit["SCHEMA_VALIDATION"] == "PASS"
    assert audit["MATCH"] == "PASS"
    assert audit["GEMINI_INPUT_PROMPT_CONTAINS_VALUE"] == "NO"
    assert audit["BRIDGE_STATE_CONTAINS_VALUE"] == "YES"


def test_hotfix113_cascade_position_is_authoritative_and_one_based():
    from unittest.mock import patch
    from providers import SEATS, call_seat
    gem = next(s for s in SEATS if s.key == "gemini")
    calls = []
    def fake_call(seat, prompt, model, credential, *args, **kwargs):
        calls.append(model)
        if model != "gemini-3.6-flash":
            from providers import ProviderError
            raise ProviderError("model unavailable", error_class="model_unavailable", status_code=404)
        return "OK"
    with patch("providers.call_official", side_effect=fake_call):
        result = call_seat(gem, "x", "", 1, False, "key", [], ("gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash"), None, "RID113")
    assert calls == ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash"]
    assert result["attempted_models"] == calls
    assert result["executed_model"] == calls[-1]
    assert result["cascade_position"] == 3


def test_hotfix113_history_persists_authoritative_cascade_position():
    from main import _run_council
    from unittest.mock import patch
    chat = {"messages": [], "request_records": [], "history_identity_ledger": [], "result_keys": [], "audit_events": []}
    gem = next(s for s in main.get_seats() if s.key == "gemini")
    result = {"seat": gem.key, "name": gem.name, "label": gem.label, "status": "SUCCESS", "mode": "official", "model": "m3", "executed_model": "m3", "provider_reported_model": "m3", "content": "ok", "attempted_models": ["m1","m2","m3"], "cascade_position": 3, "attempt_diagnostics": [], "request_id": "RID113H", "round": 1}
    with patch("main._run_round", return_value=[result]), patch("main._provider_identity_matches", return_value=True):
        _run_council("x", chat, 1, {gem.key:"key"}, [], {gem.key:("m1","m2","m3")}, "msg", "RID113H")
    msg = chat["messages"][0]
    assert msg["cascade_position"] == 3
    assert msg["attempted_models"][-1] == msg["executed_model"] == "m3"


def test_hotfix115_diagnostic_cascade_position_is_authoritative_and_one_based():
    from unittest.mock import patch
    from providers import SEATS, ProviderError, call_seat
    gem = next(s for s in SEATS if s.key == "gemini")
    calls = []
    def fake_call(seat, prompt, model, credential, *args, **kwargs):
        calls.append(model)
        if model != "m3":
            raise ProviderError("model unavailable", error_class="model_unavailable", status_code=404)
        return "provider text"
    with patch("providers.call_official", side_effect=fake_call):
        result = call_seat(gem, "x", "", 1, False, "key", [], ("m1", "m2", "m3"), None, "RID115")
    assert calls == ["m1", "m2", "m3"]
    assert result["attempted_models"] == calls
    assert result["executed_model"] == "m3"
    assert result["cascade_position"] == 3
    assert result["executed_cascade_position"] == 3
    assert result["cascade_position"] != 0
