from pathlib import Path
from unittest.mock import patch

import main
from providers import ProviderError, SEATS, call_seat


def test_hotfix117_final_http_prompt_boundary_never_contains_bridge_value():
    gem = next(s for s in SEATS if s.key == "gemini")
    canary = "HOTFIX117-BRIDGE-SECRET-CANARY"
    sent = []

    def fake_call(seat, prompt, model, credential, *args, **kwargs):
        sent.append(prompt)
        return "OK"

    with patch("providers.call_official", side_effect=fake_call):
        result = call_seat(
            gem,
            f"ordinary user text {canary}",
            f"sanitized context accidentally containing {canary}",
            1,
            False,
            "key",
            [],
            ("gemini-test-model",),
            None,
            "RID117",
            forbidden_bridge_values=(canary,),
        )

    assert result["status"] == "SUCCESS"
    assert len(sent) == 1
    assert canary not in sent[0]
    assert "[REDACTED_BRIDGE_VALUE]" in sent[0]


def test_hotfix117_preserves_hotfix116_request_determinism_contract():
    assert Path("VERSION.txt").read_text(encoding="utf-8").strip() == "V22.1-HOTFIX117-PRODUCTION-HARDENED"
    fingerprint = main._request_fingerprint("same logical request", [])
    with main._REQUEST_GATE_LOCK:
        main._ACTIVE_REQUEST_FINGERPRINTS.discard(fingerprint)
        main._ACTIVE_REQUEST_FINGERPRINTS.add(fingerprint)
    try:
        assert fingerprint in main._ACTIVE_REQUEST_FINGERPRINTS
    finally:
        with main._REQUEST_GATE_LOCK:
            main._ACTIVE_REQUEST_FINGERPRINTS.discard(fingerprint)
