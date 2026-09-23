from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
BASELINE_ZIP = ROOT.parent / "hf125" / "HOTFIX125_BRIDGE_REQUEST_BOUNDARY_CORRECTIVE_RELEASE(1).zip"
OUTPUT = ROOT.parent / "HOTFIX126_AUTHORITATIVE_ROUND_IDENTITY_FINAL.zip"

TARGET_TESTS = [
    "tests/test_hotfix126_historical_round_identity.py",
    "tests/test_hotfix126_continuation_identity.py",
    "tests/test_hotfix125_bridge_request_boundary.py",
    "tests/test_hotfix125_5_runtime_gate.py",
    "tests/test_hotfix145_conversation_runtime.py",
]


def baseline_members() -> set[str]:
    with zipfile.ZipFile(BASELINE_ZIP) as zf:
        return set(zf.namelist())


def validate_preservation() -> None:
    baseline = {m for m in baseline_members() if not m.endswith("/")}
    current = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file()}
    missing = sorted(baseline - current)
    if missing:
        raise SystemExit(f"HOTFIX125 members removed: {missing}")


def run_tests() -> None:
    subprocess.run([sys.executable, "-m", "pytest", "-q", *TARGET_TESTS], cwd=ROOT, check=True)


def package() -> dict:
    if OUTPUT.exists():
        OUTPUT.unlink()
    baseline = {m for m in baseline_members() if not m.endswith("/")}
    new_members = {
        "HOTFIX126_RELEASE_GATE.py",
        "tests/test_hotfix126_historical_round_identity.py",
    }
    package_members = sorted(baseline | new_members)
    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel in package_members:
            path = ROOT / rel
            if not path.is_file():
                raise SystemExit(f"Missing package member: {rel}")
            zf.write(path, rel)
    with zipfile.ZipFile(OUTPUT) as zf:
        names = zf.namelist()
        if len(names) != len(set(names)):
            raise SystemExit("Duplicate ZIP members")
        packaged = set(names)
        missing = sorted(baseline - packaged)
        if missing:
            raise SystemExit(f"Packaged release removed HOTFIX125 members: {missing}")
    digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    manifest = {
        "release": "HOTFIX126",
        "baseline": BASELINE_ZIP.name,
        "baseline_file_members_preserved": True,
        "zip": OUTPUT.name,
        "zip_member_count": len(names),
        "new_members": sorted(new_members),
        "sha256": digest,
        "target_tests": TARGET_TESTS,
    }
    (ROOT / "HOTFIX126_FILE_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (ROOT.parent / (OUTPUT.name + ".sha256")).write_text(f"{digest}  {OUTPUT.name}\n", encoding="utf-8")
    return {"zip": str(OUTPUT), "members": len(names), "sha256": digest, "baseline_members_preserved": len(baseline)}


def main() -> int:
    validate_preservation()
    run_tests()
    result = package()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
