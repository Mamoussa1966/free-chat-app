import main


def test_bridge_evidence_is_finalized_once_after_round_completion():
    bridge = main.SharedContextBridge(request_id="req-final", round_no=1, application_owned_test=True)
    bridge.seed_application_state("BRIDGE_RESULT", "CANARY", source="DeepSeek", source_seat=7)
    bridge.commit(type("Seat", (), {"room_slot": 2})())
    bridge.barrier()
    bridge.read("BRIDGE_RESULT", type("Seat", (), {"room_slot": 2})())
    audit = bridge.seal_runtime_audit(user_prompt="transactional bridge isolation")
    assert audit["WRITE"] == "PASS"
    assert audit["VALIDATE"] == "PASS"
    assert audit["COMMIT"] == "PASS"
    assert audit["BARRIER"] == "PASS"
    assert audit["READ"] == "PASS"
    assert audit["SOURCE"] == "DeepSeek / Seat 7"
    assert audit["TARGET"] == "Gemini / Seat 2"
    assert all(int(row.get("target_seat", 0) or 0) == 2 for row in bridge.transaction_trace())
