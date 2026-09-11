from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CURRENT = "HOTFIX14"

def test_no_stale_hotfix_markers_in_release_sources():
    stale = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix in {".zip", ".pyc", ".pyo"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if path.name == "test_hotfix14_release_consistency.py":
            continue
        for n in range(1, 14):
            if re.search(r"\bHOTFIX" + str(n) + r"\b", text):
                stale.append(f"{path}:{n}")
    assert not stale, "stale release markers: " + ", ".join(stale)

def test_version_is_hotfix14_everywhere_declared():
    assert (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip().endswith(CURRENT)
