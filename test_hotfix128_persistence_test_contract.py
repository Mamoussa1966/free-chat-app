from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "HOTFIX128_PERSISTENCE_TEST_CONTRACT.md"

def _text():
    return CONTRACT.read_text(encoding="utf-8")

def test_hotfix128_active_contract_uses_request2_round2_as_positive_mapping():
    text = _text()
    assert "Message 2 → Request 2 → Round 2" in text
    assert "Request 2 → Round 1 = FALSE" in text
    assert "REQUEST_2 → ROUND_2" in text
    assert "REQUEST_2 → ROUND_1 = FALSE" in text

def test_hotfix128_does_not_define_request2_round1_as_positive_acceptance():
    text = _text()
    assert "REQUEST_2 → ROUND_1 = PASS" not in text
    assert "REQUEST_2 → ROUND_1 = TRUE" not in text

def test_hotfix128_contract_requires_fail_closed_corruption_proof():
    text = _text()
    for required in (
        "request_2_round_2_mapping = FALSE",
        "canonical_round_sequence_proven = FALSE",
        "conversation_runtime_audit != PASS",
        "overall_authoritative_status = NOT_PROVEN أو FAIL",
        "agent prose = NOT_USED",
        "UI labels = NOT_USED",
        "latest-request projection = NOT_USED",
    ):
        assert required in text
