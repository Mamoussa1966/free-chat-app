import pytest

import main
from providers import Seat


def _bridge():
    bridge = main.SharedContextBridge(request_id="target-seat-test", round_no=1, strict_live_source=True)
    bridge._source_execution_proven = True
    bridge._values["BRIDGE_RESULT"] = {"write_origin": "PROVIDER_UNTRUSTED_DATA", "value": "opaque-test-value", "source_seat": 7}
    return bridge


def _seat(key, slot):
    return Seat(key, key, key, (f"{key.upper()}_API_KEY",), (f"{key.upper()}_FREE_MODELS",), "", key, slot)


def test_strict_live_commit_rejects_missing_target_seat():
    bridge = _bridge()
    with pytest.raises(RuntimeError, match="verified Gemini target seat 2"):
        bridge.commit(None)
    assert bridge._terminal_state == "OPEN"
    assert not any(e.get("phase") == "COMMIT" for e in bridge._runtime_bridge_evidence["events"])


def test_strict_live_commit_rejects_wrong_target_identity():
    bridge = _bridge()
    with pytest.raises(RuntimeError, match="verified Gemini target seat 2"):
        bridge.commit(_seat("claude", 3))
    assert bridge._terminal_state == "OPEN"


def test_strict_live_commit_binds_verified_gemini_seat_two():
    bridge = _bridge()
    bridge.commit(_seat("gemini", 2))
    event = next(e for e in bridge._runtime_bridge_evidence["events"] if e.get("phase") == "COMMIT")
    assert event["target_seat"] == 2
    assert bridge._terminal_state == "COMMITTED"



def test_hotfix16417_live_write_does_not_assume_target_before_commit():
    bridge = main.SharedContextBridge(request_id="live-target-proof", round_no=1, strict_live_source=True)
    # A raw trace row with unknown target must remain unknown; no key/source-based inference.
    bridge._record_trace(source_seat=7, source_provider="DeepSeek", target_seat=0,
                         key="BRIDGE_RESULT", write_sequence=1, commit_status="PENDING")
    row = bridge.transaction_trace()[0]
    assert row["target_seat"] == 0
    assert bridge._bridge_runtime_sequence_target_identity_status() == "NOT_PROVEN"
