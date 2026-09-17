from pathlib import Path


def test_hotfix92_core_module_is_packaged_and_versioned():
    root = Path(__file__).resolve().parents[1]
    assert (root / "production_core.py").is_file()
    assert "HOTFIX95" in (root / "VERSION.txt").read_text(encoding="utf-8")


def test_main_uses_production_lifecycle():
    root = Path(__file__).resolve().parents[1]
    source = (root / "main.py").read_text(encoding="utf-8")
    assert "RequestLifecycle.begin" in source
    assert "lifecycle.start_round" in source
    assert "lifecycle.finish_round" in source
