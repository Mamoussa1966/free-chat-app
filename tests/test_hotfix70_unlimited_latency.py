from pathlib import Path
import main
import providers


def test_hotfix70_has_no_artificial_provider_or_seat_timeout():
    assert providers.REQUEST_TIMEOUT is None
    assert providers.CASCADE_MODEL_TIMEOUT_SECONDS is None
    assert providers.PROVIDER_SEAT_BUDGET_SECONDS is None
    assert providers.GEMINI_REQUEST_TIMEOUT_SECONDS is None


def test_hotfix70_council_has_no_global_execution_deadline():
    source = Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8")
    assert "MAX_EXECUTION_SECONDS = None" in source
    assert "deadline = None" in source


def test_global_execution_timeout_is_opt_in_and_bounded(monkeypatch):
    monkeypatch.setattr(main, "get_secret", lambda names: "60" if tuple(names) == ("COUNCIL_EXECUTION_TIMEOUT_SECONDS",) else None)
    assert main._configured_execution_timeout_seconds() == 60.0


def test_invalid_global_execution_timeout_fails_back_to_legacy_unlimited(monkeypatch):
    monkeypatch.setattr(main, "get_secret", lambda names: "not-a-number" if tuple(names) == ("COUNCIL_EXECUTION_TIMEOUT_SECONDS",) else None)
    assert main._configured_execution_timeout_seconds() is None
