import main


def test_hotfix84_user_bridge_declaration_is_available_to_later_provider():
    bridge = main.SharedContextBridge()
    bridge.append_user_declarations("BRIDGE_TOKEN = COUNCIL-BRIDGE-TEST-7319")
    snap = bridge.snapshot()
    assert "Key: BRIDGE_TOKEN" in snap
    assert "Value: COUNCIL-BRIDGE-TEST-7319" in snap


def test_hotfix84_provider_bridge_write_is_attributed():
    bridge = main.SharedContextBridge()
    seat = next(s for s in main.get_seats() if s.key == "deepseek")
    bridge.append_agent_output(seat, {
        "status": "SUCCESS",
        "content": "BRIDGE_WRITE: BRIDGE_RESULT = DEEPSEEK-WROTE-7",
        "executed_model": "deepseek-flash",
    })
    snap = bridge.snapshot()
    assert "Source seat: 7" in snap
    assert "Source provider: DeepSeek" in snap
    assert "Key: BRIDGE_RESULT" in snap
    assert "Value: DEEPSEEK-WROTE-7" in snap
