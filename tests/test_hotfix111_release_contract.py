from pathlib import Path
import re


def test_hotfix111_version_is_canonical():
    version = Path("VERSION.txt").read_text(encoding="utf-8").strip()
    assert version == "V22.1-HOTFIX120.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE"
    assert Path("providers.py").read_text(encoding="utf-8").count(version) >= 1
    assert "APP_VERSION = PROVIDER_VERSION" in Path("main.py").read_text(encoding="utf-8")


def test_hotfix111_required_tree_is_intact():
    required = [
        "app.py", "main.py", "providers.py", "production_core.py",
        "production_core_harness.py", "production_core_test_runner.py",
        "attachment_utils.py", "gitops_layer.py", "build_release.py",
        "VERSION.txt", "README.md", "RELEASE_NOTES.md",
        ".streamlit/secrets.toml.example",
    ]
    missing = [p for p in required if not Path(p).is_file()]
    assert not missing, missing


def test_hotfix111_free_only_contract_remains_explicit():
    providers = Path("providers.py").read_text(encoding="utf-8")
    main = Path("main.py").read_text(encoding="utf-8")
    assert "MAX_MODELS_PER_SEAT = 10" in providers
    assert "Free #1" in main and "Free #10" in main
    assert "local_engine" not in main
    assert "generate_local" not in main


def test_hotfix111_harness_reports_current_identity():
    harness = Path("production_core_harness.py").read_text(encoding="utf-8")
    assert "HOTFIX120" in harness
    assert '"version": "V22.1-HOTFIX120.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE"' in harness
