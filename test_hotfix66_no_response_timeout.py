from pathlib import Path
import providers


def test_seat_budget_allows_explicit_cascade_to_continue():
    assert providers.CASCADE_MODEL_TIMEOUT_SECONDS is None
    assert providers.PROVIDER_SEAT_BUDGET_SECONDS is None


def test_main_does_not_render_timeout_as_terminal_no_response_label():
    source = Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8")
    assert "NO_RESPONSE_AFTER_CASCADE" in source
    assert 'if display_class == "TIMEOUT":' in source
