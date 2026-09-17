from pathlib import Path

import production_core_test_runner as runner


def test_runner_is_application_local_and_uses_harness():
    source = Path(runner.__file__).read_text(encoding="utf-8")
    assert "production_core_harness" in source
    assert "run_production_core_tests" in source


def test_runner_reports_current_release_identity():
    assert runner.VERSION == "V22.1-HOTFIX95-PRODUCTION-HARDENED"


def test_streamlit_ui_exposes_local_test_runner_button():
    source = Path("main.py").read_text(encoding="utf-8")
    assert "Run Production Core Tests" in source
    assert "run_production_core_tests()" in source
