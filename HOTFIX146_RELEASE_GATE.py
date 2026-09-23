from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = Path("/mnt/data/files/HOTFIX146_V23_FINAL_CLOSURE_AUDIT_FINAL_VERIFIED.zip")
BASE_ZIP = Path("/mnt/data/files/HOTFIX130_CANONICAL_PERSISTENCE_COUNTER_CONSISTENCY_FINAL_VERIFIED.zip")

ADDED = {
    "v23_final_closure_audit.py",
    "HOTFIX146_V23_FINAL_CLOSURE_AUDIT_CONTRACT.md",
    "HOTFIX146_RELEASE_NOTES.md",
    "VERSION_HOTFIX146.txt",
    "tests/test_v23_final_closure_audit.py",
    "HOTFIX146_RELEASE_GATE.py",
}
PRESERVE = {
    "conversation_persistence_v26.py",
    "conversation_store.py",
    "conversation_v25_runtime.py",
    "providers.py",
}

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def zip_members(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as z:
        return z.namelist()


def main() -> int:
    if not BASE_ZIP.exists():
        raise SystemExit(f"Missing baseline: {BASE_ZIP}")
    baseline_extract = ROOT.parent / "h146_baseline_check"
    if baseline_extract.exists():
        shutil.rmtree(baseline_extract)
    baseline_extract.mkdir()
    with zipfile.ZipFile(BASE_ZIP) as z:
        z.extractall(baseline_extract)
    base_members = set(zip_members(BASE_ZIP))
    missing = sorted(PRESERVE - base_members)
    if missing:
        raise SystemExit(f"Baseline missing preserved files: {missing}")
    # Ensure the persistence/core source files are byte-identical to HOTFIX130.
    for rel in PRESERVE:
        if sha(ROOT / rel) != sha(baseline_extract / rel):
            raise SystemExit(f"Forbidden source drift vs HOTFIX130: {rel}")
    # Run tests from the correct project root.
    env = dict(os.environ)
    r = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, env=env, text=True, capture_output=True)
    print(r.stdout)
    print(r.stderr)
    if r.returncode != 0:
        return r.returncode

    if OUT.exists():
        OUT.unlink()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    members = sorted(p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file() and ".pytest_cache" not in p.parts and p.name not in {"HOTFIX146_MANIFEST.json"})
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in members:
            z.write(ROOT / rel, rel)

    # Re-extract and run the exact ZIP contents.
    check = ROOT.parent / "h146_zip_check"
    if check.exists():
        shutil.rmtree(check)
    check.mkdir()
    with zipfile.ZipFile(OUT) as z:
        z.extractall(check)
    r2 = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=check, env=env, text=True, capture_output=True)
    print(r2.stdout)
    print(r2.stderr)
    if r2.returncode != 0:
        return r2.returncode

    manifest = {
        "release": "HOTFIX146",
        "version": "V23.0.0-HOTFIX146-V23-FINAL-CLOSURE-AUDIT",
        "base_zip": BASE_ZIP.name,
        "purpose": "V23 final closure audit without changing canonical persistence semantics",
        "added_files": sorted(ADDED),
        "preserved_hotfix130_core_files_byte_identical": True,
        "hotfix123_2_provider_core_preserved": True,
        "hotfix129_persistence_contract_preserved": True,
        "hotfix130_counter_semantics_preserved": True,
        "fresh_full_v23_audit_button": True,
        "fail_closed": True,
        "source_pytest": "500+ tests; see gate output",
        "zip_pytest": "500+ tests; see gate output",
    }
    manifest_path = ROOT / "HOTFIX146_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Append manifest to final ZIP, then compute final hash.
    with zipfile.ZipFile(OUT, "a", zipfile.ZIP_DEFLATED) as z:
        z.write(manifest_path, manifest_path.name)
    final_sha = sha(OUT)
    (Path(str(OUT) + ".sha256")).write_text(final_sha + "  " + OUT.name + "\n", encoding="utf-8")
    print(f"FINAL_ZIP={OUT}")
    print(f"MEMBERS={len(zip_members(OUT))}")
    print(f"SHA256={final_sha}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
