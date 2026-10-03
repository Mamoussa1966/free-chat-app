import main
from providers import SEATS


def test_diagnostic_bridge_token_does_not_reject_dispatch_boundary():
    # The user's diagnostic request may name BRIDGE_RESULT; that text must not
    # be mistaken for a provider-layer leak.
    main._assert_provider_boundary(
        "Test BRIDGE_RESULT and bridge controls here",
        "Reply to the diagnostic request without bridge values.",
        [("BRIDGE_RESULT", "DS7k4mQ9zP2xT8")],
    )


def test_dispatch_gate_accepts_configured_explicit_free_model():
    seat = next(s for s in SEATS if s.key == "gemini")
    ok, reason = main._dispatch_gate(seat, "abc123", 1, "secret", ("gemini-test-free",))
    assert ok is True
    assert reason == "READY_FREE_MODEL"


def test_dispatch_gate_rejects_only_invalid_configuration():
    seat = next(s for s in SEATS if s.key == "gemini")
    ok, reason = main._dispatch_gate(seat, "abc123", 1, "", ("gemini-test-free",))
    assert ok is False
    assert reason == "CREDENTIAL_MISSING"
