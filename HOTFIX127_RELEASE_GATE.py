from __future__ import annotations
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent
BASELINE_ZIP = ROOT.parent / "HOTFIX126_AUTHORITATIVE_ROUND_IDENTITY_FINAL_VERIFIED.zip"
OUTPUT = ROOT.parent / "HOTFIX127_AUTHORITATIVE_ROUND_CONTRACT_FINAL_VERIFIED.zip"
NEW_MEMBERS = {
    "HOTFIX127_RELEASE_GATE.py",
    "tests/test_hotfix127_authoritative_round_contract.py",
    "VERSION_HOTFIX127.txt",
}


def baseline_members() -> set[str]:
    with zipfile.ZipFile(BASELINE_ZIP) as zf:
        return {n for n in zf.namelist() if not n.endswith("/")}


def current_members() -> set[str]:
    return {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


def run_full_pytest(cwd: Path) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def validate_source() -> str:
    baseline = baseline_members()
    current = current_members()
    missing = sorted(baseline - current)
    if missing:
        raise SystemExit(f"HOTFIX126 members removed from source tree: {missing}")
    if not NEW_MEMBERS <= current:
        raise SystemExit(f"HOTFIX127 new members missing: {sorted(NEW_MEMBERS - current)}")
    return run_full_pytest(ROOT)


def package() -> Path:
    if OUTPUT.exists():
        OUTPUT.unlink()
    baseline = baseline_members()
    package_members = sorted(baseline | NEW_MEMBERS)
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
        if set(names) != set(package_members):
            raise SystemExit("ZIP member set mismatch")
    return OUTPUT


def verify_reextracted_release(zip_path: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="hotfix127_verify_") as td:
        extract = Path(td) / "release"
        extract.mkdir()
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract)
        return run_full_pytest(extract)


def main() -> int:
    source_pytest = validate_source()
    output = package()
    release_pytest = verify_reextracted_release(output)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    with zipfile.ZipFile(output) as zf:
        members = len(zf.namelist())
    manifest = {
        "version": "V23.0.0-HOTFIX127-AUTHORITATIVE-ROUND-CONTRACT-FINAL",
        "base": BASELINE_ZIP.name,
        "provider_core": "V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE",
        "purpose": "Correct Request_2→Round_2 contract and make canonical round proof record-level and fail-closed",
        "baseline_file_members_preserved": True,
        "baseline_member_count": len(baseline_members()),
        "file_count": members,
        "new_members": sorted(NEW_MEMBERS),
        "source_full_pytest": source_pytest,
        "reextracted_full_pytest": release_pytest,
        "sha256": digest,
        "regression_gate": "CANONICAL_MESSAGE_REQUEST_ROUND_IDENTITY + MONOTONIC_SELECTED_ROUND_SEQUENCE",
        "required_positive": "MESSAGE_1→REQUEST_1→ROUND_1; MESSAGE_2→REQUEST_2→ROUND_2 for exact-two history",
        "required_negative": "REQUEST_2→ROUND_1 must be false",
        "fail_closed": "MISSING_OR_AMBIGUOUS_OR_CONTRADICTORY_CANONICAL_IDENTITY => NOT_PROVEN/FAIL",
    }
    (ROOT / "HOTFIX127_FILE_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (ROOT.parent / (output.name + ".sha256")).write_text(f"{digest}  {output.name}\n", encoding="utf-8")
    print(json.dumps({"zip": str(output), "members": members, "sha256": digest, "source_pytest": source_pytest, "reextracted_pytest": release_pytest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
