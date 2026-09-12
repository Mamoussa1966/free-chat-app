from pathlib import Path
import providers


def test_stable_public_error_taxonomy_contains_all_expected_classes():
    assert providers._canonical_error_classification("model_not_found_or_invalid") == "MODEL_UNAVAILABLE"
    assert providers._canonical_error_classification("billing_or_quota") == "QUOTA_EXCEEDED"
    assert providers._canonical_error_classification("http_429_rate_limit_or_quota") == "RATE_LIMITED"
    assert providers._canonical_error_classification("http_401_authentication_failed") == "AUTHENTICATION_ERROR"
    assert providers._canonical_error_classification("provider_server") == "API_ERROR"
    assert providers._canonical_error_classification("network") == "NETWORK_ERROR"
    assert providers._canonical_error_classification("timeout") == "TIMEOUT"


def test_build_release_has_isolated_sandbox_and_environment_scrubbing():
    source = Path("build_release.py").read_text(encoding="utf-8")
    assert "TemporaryDirectory" in source
    assert "secret_markers" in source
    assert "PYTEST_DISABLE_PLUGIN_AUTOLOAD" in source
    assert "cwd=sandbox" in source
    assert 'cwd=ROOT' not in source


def test_release_preserves_all_current_test_files():
    root = Path(__file__).resolve().parents[1]
    test_files = sorted((root / "tests").glob("test_*.py"))
    assert len(test_files) == 20
    assert "test_hotfix17_fixes.py" in {p.name for p in test_files}
    assert "test_hotfix18_fixes.py" in {p.name for p in test_files}
    assert "test_hotfix19_fixes.py" in {p.name for p in test_files}
