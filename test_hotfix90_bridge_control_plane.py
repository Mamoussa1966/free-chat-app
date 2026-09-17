import providers

def test_hotfix90_bridge_control_plane_is_explicit_and_provider_agnostic():
    seats = providers.get_seats()
    ds = next(s for s in seats if s.key == "deepseek")
    gem = next(s for s in seats if s.key == "gemini")
    dp = providers._prompt("HOTFIX BRIDGE TRANSACTION TEST", "BRIDGE READ AVAILABLE (VALUE NOT IN PROMPT):\nKey: BRIDGE_RESULT", 1, ds, "deepseek-flash")
    gp = providers._prompt("HOTFIX BRIDGE TRANSACTION TEST", "BRIDGE READ AVAILABLE (VALUE NOT IN PROMPT):\nKey: BRIDGE_RESULT", 1, gem, "gemini-3.8-flash")
    assert "BRIDGE CONTROL-PLANE CONTRACT" in dp
    assert "BRIDGE_WRITE: BRIDGE_RESULT = <value>" in dp
    assert "BRIDGE CONTROL-PLANE CONTRACT" in gp
    assert "BRIDGE_READ: BRIDGE_RESULT" in gp
    assert "<value>" not in gp.split("BRIDGE CONTROL-PLANE CONTRACT", 1)[0]
    assert "<value>" in gp
