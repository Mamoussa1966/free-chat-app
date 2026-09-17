from pathlib import Path

import production_core_harness as harness


def test_hotfix91_file_manifest_is_preserved():
    result = harness.check_file_preservation()
    assert result["passed"], result["missing"]


def test_harness_core_probes_are_deterministic():
    results = harness.run_core_probes()
    failed = {k: v for k, v in results.items() if not v["passed"]}
    assert not failed, failed


def test_harness_has_real_pytest_executor():
    source = Path(harness.__file__).read_text(encoding="utf-8")
    assert '"-m", "pytest", "-q"' in source
    assert "PYTEST_DISABLE_PLUGIN_AUTOLOAD" in source
