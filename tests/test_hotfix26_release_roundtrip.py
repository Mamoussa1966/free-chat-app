from pathlib import Path
import os
import re


def test_release_builder_reextracts_and_retests_artifact():
    source = Path("build_release.py").read_text(encoding="utf-8")
    assert "verify_extracted_release" in source
    assert "zf.extractall(sandbox)" in source
    assert "_run_suite_in_sandbox(sandbox)" in source


def test_release_builder_scrubs_credential_like_environment_variables():
    source = Path("build_release.py").read_text(encoding="utf-8")
    assert "secret_markers" in source
    assert "PYTEST_DISABLE_PLUGIN_AUTOLOAD" in source
    assert 'env["PYTHONPATH"] = str(sandbox)' in source


def test_current_release_version_is_consistent():
    root = Path(__file__).resolve().parents[1]
    version = (root / "VERSION.txt").read_text(encoding="utf-8").strip()
    assert version == "V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX27-FINAL"
    assert f'VERSION = "{version}"' in (root / "providers.py").read_text(encoding="utf-8")
    assert version in (root / "README.md").read_text(encoding="utf-8")
    assert version in (root / "RELEASE_NOTES.md").read_text(encoding="utf-8")


def test_all_existing_test_modules_are_preserved_and_new_regression_is_present():
    root = Path(__file__).resolve().parents[1]
    test_names = {p.name for p in (root / "tests").glob("test_*.py") if p.is_file()}
    expected_core = {
        "test_attachments.py", "test_core.py", "test_entrypoint.py",
        "test_gitops_layer.py", "test_hardening.py",
        "test_hotfix13_model_identity.py", "test_hotfix14_cascade_invariants.py",
        "test_hotfix14_error_classification.py", "test_hotfix14_request_history_identity.py",
        "test_hotfix17_fixes.py", "test_hotfix18_fixes.py", "test_hotfix19_fixes.py",
        "test_hotfix21_release_consistency.py", "test_hotfix21_ui_privacy.py",
        "test_provider_runtime.py", "test_v213_hardening.py", "test_v214_voice.py",
        "test_v215_resilience.py", "test_v216_hardening.py",
    }
    assert expected_core <= test_names
    assert "test_hotfix26_release_roundtrip.py" in test_names
    assert len(test_names) == 20


def test_packaged_zip_excludes_runtime_caches(tmp_path):
    import build_release
    out = tmp_path / "release.zip"
    build_release.package(out)
    import zipfile
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    assert all("__pycache__/" not in n and ".pytest_cache/" not in n for n in names)
    assert all(not n.endswith((".pyc", ".pyo")) for n in names)
