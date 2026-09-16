import re
from unittest.mock import patch
import main


def _result(seat, content, request_id="rid88", round_no=1):
    return {
        "seat": seat.key, "name": seat.name, "label": seat.label,
        "status": "SUCCESS", "mode": "official", "model": "test-model",
        "executed_model": "test-model", "provider_reported_model": "test-model",
        "content": content, "error": None, "latency": 0.001,
        "attempted_models": ["test-model"], "attempt_diagnostics": [],
        "attempt_summaries": [], "official_authenticated": True,
        "request_id": request_id, "round": round_no,
    }


def test_hotfix88_version_contract():
    import providers
    assert providers.VERSION == "V22.1-HOTFIX90-PRODUCTION-HARDENED"
    assert main.APP_VERSION == "V22.1-HOTFIX90-PRODUCTION-HARDENED"


def test_hotfix88_transaction_trace_and_prompt_redaction():
    seats = main.get_seats()
    ds = next(s for s in seats if s.key == "deepseek")
    gem = next(s for s in seats if s.key == "gemini")
    bridge = main.SharedContextBridge(request_id="rid88", round_no=1)
    generated = "DS7-R4ND-8831"
    bridge.append_agent_output(ds, _result(ds, f"BRIDGE_WRITE: BRIDGE_RESULT = {generated}"))
    prompt = bridge.prompt_snapshot(gem)
    assert generated not in prompt
    assert "Key: BRIDGE_RESULT" in prompt
    assert "BRIDGE READ AVAILABLE (VALUE NOT IN PROMPT)" in prompt
    bridge.commit()
    bridge.barrier()
    assert bridge.read("BRIDGE_RESULT", gem) == generated
    trace = bridge.trace
    assert trace[-1]["bridge_id"] == trace[0]["bridge_id"]
    assert trace[-1]["round_id"] == 1
    assert trace[-1]["source_seat"] == ds.room_slot
    assert trace[-1]["source_provider"] == ds.name
    assert trace[-1]["target_seat"] == gem.room_slot
    assert trace[-1]["key"] == "BRIDGE_RESULT"
    assert trace[-1]["write_sequence"] == 1
    assert trace[-1]["commit_status"] == "COMMITTED"
    assert trace[-1]["read_sequence"] == 1
    assert trace[-1]["schema_validation"] == "PASS"
    assert trace[-1]["request_id"] == "rid88"


def test_hotfix88_barrier_blocks_read_before_commit():
    seats = main.get_seats()
    ds = next(s for s in seats if s.key == "deepseek")
    gem = next(s for s in seats if s.key == "gemini")
    bridge = main.SharedContextBridge(request_id="rid88b", round_no=1)
    bridge.append_agent_output(ds, _result(ds, "BRIDGE_WRITE: BRIDGE_RESULT = SECRET-RANDOM-88"))
    assert bridge.read("BRIDGE_RESULT", gem) is None
    bridge.commit()
    assert bridge.read("BRIDGE_RESULT", gem) is None
    bridge.barrier()
    assert bridge.read("BRIDGE_RESULT", gem) == "SECRET-RANDOM-88"


def test_hotfix88_gemini_read_request_is_resolved_after_response():
    seats = main.get_seats()
    ds = next(s for s in seats if s.key == "deepseek")
    gem = next(s for s in seats if s.key == "gemini")
    bridge = main.SharedContextBridge(request_id="rid88c", round_no=1)
    generated = "DS7-Q9M2-Z8K1"
    bridge.append_agent_output(ds, _result(ds, f"BRIDGE_WRITE: BRIDGE_RESULT = {generated}"))
    bridge.commit(); bridge.barrier()
    gem_result = _result(gem, "BRIDGE_READ: BRIDGE_RESULT")
    resolution = bridge.consume_read_requests(gem, gem_result)
    assert resolution["schema_validation"] == "PASS"
    assert resolution["reads"] == [{"key": "BRIDGE_RESULT", "value": generated, "available": True}]
    assert generated not in str(gem_result)
