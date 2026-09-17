from pathlib import Path
import providers


def test_timeout_is_internal_and_public_no_response_is_distinct():
    assert providers.ERROR_CLASS_TIMEOUT == "TIMEOUT"
    assert providers.ERROR_CLASS_NO_RESPONSE == "NO_RESPONSE_AFTER_CASCADE"
    assert providers._canonical_error_classification("timeout") == "TIMEOUT"


def test_main_neutralizes_timeout_for_public_failure_rendering():
    source = Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8")
    assert 'if display_class == "TIMEOUT":' in source
    assert "NO_RESPONSE_AFTER_CASCADE" in source and 'if display_class == "TIMEOUT":' in source
    assert "did not complete a response in the current attempt" in source
