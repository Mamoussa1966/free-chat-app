from pathlib import Path
import re


def test_release_metadata_has_single_current_version():
    root = Path(__file__).resolve().parents[1]
    version = (root / "VERSION.txt").read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"V22\.1-HOTFIX123\.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE", version)

    main = (root / "main.py").read_text(encoding="utf-8")
    providers = (root / "providers.py").read_text(encoding="utf-8")
    release = (root / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    builder = (root / "build_release.py").read_text(encoding="utf-8")

    # main.py derives the display version from providers.py instead of carrying a stale literal.
    assert "APP_VERSION = PROVIDER_VERSION" in main
    assert f'VERSION = "{version}"' in providers
    assert version in release
    assert f"HOTFIX{re.search(r'HOTFIX(\d+)', version).group(1)}_2_SINGLE_REQUEST_DETERMINISM_LIVE_CASCADE.zip" in builder


def test_no_stale_hotfix_identifiers_remain_outside_this_regression_test():
    root = Path(__file__).resolve().parents[1]
    # Historical release notes and preserved tests intentionally contain older
    # HOTFIX names. This test only guards the active production metadata.
    forbidden = [re.compile(r"\bHOTFIX" + str(n) + r"\b") for n in range(1, 123)]

    paths = [root / "providers.py", root / "build_release.py", root / "VERSION.txt"]
    offenders = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in forbidden:
            if marker.search(text):
                offenders.append(f"{path.relative_to(root)}:{marker.pattern}")
    assert not offenders, "Stale release identifiers found: " + ", ".join(offenders)
