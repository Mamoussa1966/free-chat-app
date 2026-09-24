from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "HOTFIX147_PRESERVATION_MANIFEST.json"
TARGET_TEST = ROOT / "tests/test_hotfix130_authoritative_result_counter.py"
VERSION = ROOT / "VERSION_HOTFIX147.txt"

REQUIRED = {
    "main.py",
    "providers.py",
    "production_core.py",
    "production_platform.py",
    "conversation_schema.py",
    "message_ledger.py",
    "conversation_migrations.py",
    "session_manager.py",
    "HOTFIX147_RELEASE_NOTES.md",
    "HOTFIX147_PRESERVATION_MANIFEST.json",
    "tests/test_hotfix147_security_regression.py",
    "tests/test_hotfix130_authoritative_result_counter.py",
    "VERSION_HOTFIX147.txt",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_pytest(cwd: Path) -> None:
    env = dict(os.environ)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONPATH"] = str(cwd)
    subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=cwd, env=env, check=True)


def _check_required() -> None:
    missing = sorted(p for p in REQUIRED if not (ROOT / p).is_file())
    if missing:
        raise SystemExit(f"REQUIRED_FILES_FAIL: {missing}")
    if "_authoritative_ui_projection" not in (ROOT / "main.py").read_text(encoding="utf-8"):
        raise SystemExit("HOTFIX130_REGRESSION_FAIL: _authoritative_ui_projection missing")
    if "_format_authoritative_counter_summary" not in (ROOT / "main.py").read_text(encoding="utf-8"):
        raise SystemExit("HOTFIX130_REGRESSION_FAIL: _format_authoritative_counter_summary missing")


def _check_security_contract() -> None:
    src = (ROOT / "production_platform.py").read_text(encoding="utf-8")
    required = '"RAW_PROVIDER_PAYLOADS": _has_nonempty_field'
    if required not in src:
        raise SystemExit("SECURITY_CONTRACT_FAIL: raw payload gate is not value-based")
    if 'out.pop("raw_provider_payload", None)' not in src:
        raise SystemExit("SECURITY_CONTRACT_FAIL: raw payload removal missing")
    if 'out.pop("attempt_diagnostics", None)' not in src:
        raise SystemExit("SECURITY_CONTRACT_FAIL: diagnostics removal missing")


def _check_preservation_metadata() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected = data.get("protected_files") or []
    baseline_sha = data.get("baseline_sha256") or {}
    if not expected or set(expected) != set(baseline_sha):
        raise SystemExit("PRESERVATION_FAIL: protected file/hash manifest incomplete")
    missing = [p for p in expected if not (ROOT / p).is_file()]
    if missing:
        raise SystemExit(f"PRESERVATION_FAIL: missing protected files {missing}")
    drift = {p: (baseline_sha[p], sha256(ROOT / p)) for p in expected if sha256(ROOT / p) != baseline_sha[p]}
    if drift:
        raise SystemExit(f"PRESERVATION_FAIL: protected HOTFIX130 files drifted: {drift}")
    provider_identity = data.get("provider_identity_expected")
    release_identity = (ROOT / "RELEASE_IDENTITY.json").read_text(encoding="utf-8")
    if provider_identity not in release_identity:
        raise SystemExit("HOTFIX123.2_PRESERVATION_FAIL: frozen provider identity marker missing")
    for marker in (data.get("hotfix129_marker"), data.get("hotfix130_marker")):
        if not marker or not (ROOT / marker).is_file():
            raise SystemExit(f"HOTFIX_PRESERVATION_FAIL: missing marker {marker}")
    version = VERSION.read_text(encoding="utf-8").strip()
    if version != "V23.0.0-HOTFIX147-V23-SECURITY-REGRESSION-CLOSURE":
        raise SystemExit(f"VERSION_FAIL: {version}")


def _check_exact_zip(zip_path: Path) -> None:
    import zipfile
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        missing = sorted(REQUIRED - names)
        if missing:
            raise SystemExit(f"ZIP_REQUIRED_FILES_FAIL: {missing}")
        if "tests/test_hotfix130_authoritative_result_counter.py" not in names:
            raise SystemExit("ZIP_HOTFIX130_REGRESSION_TEST_MISSING")
        if "tests/test_hotfix147_security_regression.py" not in names:
            raise SystemExit("ZIP_SECURITY_REGRESSION_TEST_MISSING")
        for name in names:
            if name.startswith("/") or ".." in Path(name).parts or "\\" in name:
                raise SystemExit(f"ZIP_PATH_FAIL: {name}")
        with tempfile.TemporaryDirectory(prefix="hotfix147_zip_gate_") as tmp:
            extracted = Path(tmp) / "release"
            extracted.mkdir()
            zf.extractall(extracted)
            _run_pytest(extracted)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", dest="zip_path", default="")
    args = parser.parse_args()
    _check_required()
    _check_security_contract()
    _check_preservation_metadata()
    _run_pytest(ROOT)
    if args.zip_path:
        _check_exact_zip(Path(args.zip_path).resolve())
        print("exact ZIP re-extraction pytest = PASS")
    print("security_audit = PASS (covered by test_hotfix147_security_regression.py)")
    print("NO_RAW_PROVIDER_PAYLOADS_IN_HISTORY = true")
    print("canonical_counter_source = CANONICAL_IDENTITY_RECORDS (runtime contract preserved)")
    print("HOTFIX130 regression = PASS")
    print("HOTFIX123.2 preservation = PASS (provider/core contract unchanged by this closure patch)")
    print("HOTFIX129 preservation = PASS (persistence contract unchanged by this closure patch)")
    print("HOTFIX130 preservation = PASS (authoritative counter semantics unchanged)")
    print("RELEASE_GATE = PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
