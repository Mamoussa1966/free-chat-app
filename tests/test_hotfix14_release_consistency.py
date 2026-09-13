from pathlib import Path
import re


def test_release_metadata_has_single_current_version():
    root = Path(__file__).resolve().parents[1]
    version = (root / "VERSION.txt").read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"V22\.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX\d+-FINAL", version)

    main = (root / "main.py").read_text(encoding="utf-8")
    providers = (root / "providers.py").read_text(encoding="utf-8")
    release = (root / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    builder = (root / "build_release.py").read_text(encoding="utf-8")

    # main.py derives the display version from providers.py instead of carrying a stale literal.
    assert "APP_VERSION = PROVIDER_VERSION" in main
    assert f'VERSION = "{version}"' in providers
    assert version in release
    assert "HOTFIX39_DEEPSEEK_ADAPTER_FINAL.zip" in builder


def test_no_stale_release_version_literals_remain_outside_this_regression_test():
    root = Path(__file__).resolve().parents[1]
    version = (root / "VERSION.txt").read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"V22\.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX\d+-FINAL", version)
    assert "APP_VERSION = PROVIDER_VERSION" in (root / "main.py").read_text(encoding="utf-8")
    for path in (root / "providers.py", root / "README.md", root / "RELEASE_NOTES.md"):
        assert version in path.read_text(encoding="utf-8", errors="replace")
