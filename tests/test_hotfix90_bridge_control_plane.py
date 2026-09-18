import providers

def test_hotfix90_bridge_control_plane_is_explicit_and_provider_agnostic():
    seats = providers.get_seats()
    ds = next(s for s in seats if s.key == "deepseek")
    gem = next(s for s in seats if s.key == "gemini")
    dp = providers._prompt("HOTFIX BRIDGE TRANSACTION TEST", "BRIDGE CONTEXT CAPABILITY (SANITIZED)", 1, ds, "deepseek-flash")
    gp = providers._prompt("HOTFIX BRIDGE TRANSACTION TEST", "BRIDGE CONTEXT CAPABILITY (SANITIZED)", 1, gem, "gemini-3.8-flash")
    assert "BRIDGE CONTROL-PLANE CONTRACT" in dp
    assert "BRIDGE_WRITE: BRIDGE_RESULT = <value>" in dp
    assert "BRIDGE CONTROL-PLANE CONTRACT" in gp
    assert "BRIDGE_RESULT" not in gp
    assert "BRIDGE_READ" not in gp
    assert "bridge value" in gp.lower()
