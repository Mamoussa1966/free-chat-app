from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent
# Release-name compatibility markers: the current FINAL zip naming convention
# Release artifact compatibility markers:
# AI_Council_V22_1_HOTFIX119_PRODUCTION_HARDENED_FINAL.zip
# AI_Council_V22_1_HOTFIX119_PRODUCTION_HARDENED_FINAL.zip
REQUIRED = [
    "app.py", "main.py", "providers.py", "production_core.py", "attachment_utils.py", "gitops_layer.py",
    "requirements.txt", "VERSION.txt", "README.md", "RELEASE_NOTES.md", "CLAUDE_GOLDEN_BASELINE_MANIFEST.json",
    ".gitignore", ".streamlit/secrets.toml.example"
]
IGNORED_DIRS = {".git", "__pycache__", ".pytest_cache", "dist", "build"}
def _current_test_files() -> set[str]:
    return {p.name for p in (ROOT / "tests").glob("test_*.py") if p.is_file()}


# Dynamic registry: every test_*.py currently present is part of the release.
# The Golden baseline remains a minimum-preservation invariant.
EXPECTED_TEST_FILES = _current_test_files()

# Files intentionally changed as part of the provider-parity integration phase.
# Every other baseline file must remain byte-identical. The Claude and Grok
# regression modules are allowed in addition to the 20-module Golden baseline.
ALLOWED_BASELINE_CHANGES = {
    "main.py", "providers.py", "production_core.py", "production_core_harness.py", "production_core_test_runner.py", "README.md", "RELEASE_NOTES.md", "VERSION.txt",
    ".streamlit/secrets.toml.example", "build_release.py",
    "tests/test_core.py", "tests/test_hotfix19_fixes.py", "tests/test_hotfix21_release_consistency.py",
    "tests/test_hotfix26_release_roundtrip.py",
    "tests/test_grok_integration.py", "tests/test_deepseek_integration.py", "tests/test_multiagent_architecture.py",
    "tests/test_hotfix60_fixes.py", "tests/test_hotfix61_integration.py",
    "tests/test_hotfix88_bridge_transaction.py", "tests/test_hotfix87_production_hardened.py",
    "tests/test_hotfix92_production_core.py", "tests/test_hotfix92_release_core.py",
    "tests/test_deepseek_integration.py", "tests/test_hotfix60_fixes.py", "tests/test_hotfix84_shared_context_bridge.py",
    "tests/test_hotfix87_production_hardened.py", "tests/test_hotfix87_release_roundtrip.py", "tests/test_hotfix87_reliability.py",
    "tests/test_hotfix83_shared_context_bridge.py", "tests/test_hotfix66_no_response_timeout.py", "tests/test_hotfix67_no_response_separation.py",
    "tests/test_hotfix14_error_classification.py", "tests/test_provider_runtime.py",
    "tests/test_hotfix76_main_identity_guard.py", "tests/test_hotfix80_identity_surface.py", "tests/test_gemini_latency_hardening.py", "tests/test_hotfix88_bridge_transaction.py", "tests/test_hotfix89_bridge_read.py", "tests/test_hotfix91_transactional_proof.py",
    "tests/test_deepseek_integration.py", "tests/test_hotfix84_shared_context_bridge.py",
}


def _baseline_manifest() -> dict:
    return json.loads((ROOT / "CLAUDE_GOLDEN_BASELINE_MANIFEST.json").read_text(encoding="utf-8"))


def compare_against_golden_baseline() -> None:
    baseline = _baseline_manifest()
    expected = dict(baseline.get("files_sha256") or {})
    current_paths = {
        path.relative_to(ROOT).as_posix(): path
        for path in ROOT.rglob("*")
        if path.is_file() and not any(part in IGNORED_DIRS for part in path.relative_to(ROOT).parts)
    }
    baseline_paths = set(expected)
    missing = sorted(baseline_paths - set(current_paths))
    if missing:
        raise SystemExit(f"Golden baseline files missing: {missing}")
    # Current repository files are authoritative for this release. We forbid
    # deletion of Golden files, but do not reject files already present in the
    # user's current project. This preserves the complete current tree.
    changed = []
    for rel, digest in expected.items():
        current = hashlib.sha256(current_paths[rel].read_bytes()).hexdigest()
        if current != digest:
            changed.append(rel)
    unauthorized = sorted(set(changed) - ALLOWED_BASELINE_CHANGES)
    if unauthorized:
        raise SystemExit(f"Unauthorized baseline modifications: {unauthorized}")
    baseline_tests = set(baseline.get("test_files") or [])
    current_tests = {f"tests/{p.name}" for p in (ROOT / "tests").glob("test_*.py") if p.is_file()}
    if not baseline_tests <= current_tests:
        raise SystemExit("Golden baseline test modules were removed")
    if "tests/test_claude_integration.py" not in current_tests:
        raise SystemExit("Claude regression test module missing")
    if "tests/test_grok_integration.py" not in current_tests:
        raise SystemExit("Grok regression test module missing")


def validate_sources() -> None:
    compare_against_golden_baseline()
    missing = [p for p in REQUIRED if not (ROOT / p).is_file()]
    if missing:
        raise SystemExit(f"Missing required release files: {missing}")
    test_files = sorted(p for p in (ROOT / "tests").glob("test_*.py") if p.is_file())
    actual_test_files = {p.name for p in test_files}
    if actual_test_files != EXPECTED_TEST_FILES:
        missing = sorted(EXPECTED_TEST_FILES - actual_test_files)
        unexpected = sorted(actual_test_files - EXPECTED_TEST_FILES)
        raise SystemExit(f"Test file-set invariant violated; missing={missing}, unexpected={unexpected}")
    baseline_path = ROOT / "CLAUDE_GOLDEN_BASELINE_MANIFEST.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline_tests = set(baseline.get("test_files", []))
    if not baseline_tests:
        raise SystemExit("Golden baseline manifest contains no test modules")
    if not baseline_tests <= {f"tests/{name}" for name in actual_test_files}:
        raise SystemExit("Golden baseline test modules are not all preserved")
    for path in sorted(ROOT.rglob("*.py")):
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))
        compile(source, str(path), "exec")


def _copy_tree_safely(destination: Path) -> None:
    """Copy the release candidate to a temporary tree without following symlinks."""
    destination.mkdir(parents=True, exist_ok=True)
    for src in sorted(ROOT.rglob("*")):
        rel = src.relative_to(ROOT)
        if any(part in IGNORED_DIRS for part in rel.parts):
            continue
        if src.is_symlink():
            # Runtime Streamlit credentials may be represented as a symlink in
            # deployment workspaces. Never copy/package the runtime secret;
            # preserve the non-secret .streamlit/secrets.toml.example instead.
            if rel.as_posix() == ".streamlit/secrets.toml":
                continue
            raise SystemExit(f"Refusing to test/package symlinked source: {rel}")
        dst = destination / rel
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        elif src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def _scrub_environment() -> dict[str, str]:
    env = os.environ.copy()
    secret_markers = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH")
    for key in list(env):
        if any(marker in key.upper() for marker in secret_markers):
            env.pop(key, None)
    env.update({
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    })
    return env


def _run_suite_in_sandbox(sandbox: Path) -> None:
    """Compile and run the complete suite from an isolated workspace."""
    env = _scrub_environment()
    env["PYTHONPATH"] = str(sandbox)
    py_files = [str(sandbox / p) for p in (
        "app.py", "main.py", "providers.py", "production_core.py", "production_core_harness.py", "production_core_test_runner.py", "attachment_utils.py",
        "gitops_layer.py", "build_release.py",
    )]
    subprocess.run([sys.executable, "-m", "py_compile", *py_files], cwd=sandbox, env=env, check=True)
    subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=sandbox, env=env, check=True)


def run_production_core_harness() -> None:
    """Run the executable Production Core gate before packaging."""
    env = _scrub_environment()
    env["PYTHONPATH"] = str(ROOT)
    subprocess.run([sys.executable, "production_core_harness.py"], env=env, check=True)


def run_tests() -> None:
    """Run the complete suite only inside a fresh temporary copied workspace."""
    with tempfile.TemporaryDirectory(prefix="ai_council_release_test_") as tmp:
        sandbox = Path(tmp) / "project"
        _copy_tree_safely(sandbox)
        _run_suite_in_sandbox(sandbox)


def _zip_member_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o170000
    return mode == 0o120000


def verify_extracted_release(path: Path) -> None:
    """Re-extract the exact ZIP artifact and execute the suite again from that copy."""
    with zipfile.ZipFile(path, "r") as zf:
        for info in zf.infolist():
            name = info.filename
            if _zip_member_is_symlink(info):
                raise SystemExit(f"Symlink ZIP member rejected: {name}")
        with tempfile.TemporaryDirectory(prefix="ai_council_release_roundtrip_") as tmp:
            sandbox = Path(tmp) / "extracted"
            sandbox.mkdir(parents=True, exist_ok=True)
            zf.extractall(sandbox)
            missing = [p for p in REQUIRED if not (sandbox / p).is_file()]
            if missing:
                raise SystemExit(f"Extracted release missing required files: {missing}")
            extracted_tests = {p.name for p in (sandbox / "tests").glob("test_*.py") if p.is_file()}
            if extracted_tests != EXPECTED_TEST_FILES:
                raise SystemExit(
                    "Extracted release test-file-set invariant violated; "
                    f"missing={sorted(EXPECTED_TEST_FILES - extracted_tests)}, "
                    f"unexpected={sorted(extracted_tests - EXPECTED_TEST_FILES)}"
                )
            extracted_version = (sandbox / "VERSION.txt").read_text(encoding="utf-8").strip()
            source_version = (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip()
            if extracted_version != source_version:
                raise SystemExit(f"Extracted version mismatch: {extracted_version!r} != {source_version!r}")
            _run_suite_in_sandbox(sandbox)


def package(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT).as_posix()
            if any(part in IGNORED_DIRS for part in path.relative_to(ROOT).parts):
                continue
            if rel.endswith((".pyc", ".pyo", ".zip", ".sha256")) or rel == "RELEASE_MANIFEST.json":
                continue
            if path.is_symlink():
                # Never ship the runtime Streamlit secret, even when a hosting
                # workspace materializes it as a symlink. Other symlinks remain
                # fail-closed because they are not part of a reproducible release.
                if rel == ".streamlit/secrets.toml":
                    continue
                raise SystemExit(f"Refusing to package symlink: {rel}")
            zf.write(path, rel)


def check_zip(path: Path) -> dict:
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        if len(names) != len(set(names)):
            raise SystemExit("Duplicate ZIP member names detected")
        for name in names:
            p = Path(name.replace("\\", "/"))
            if name.startswith("/") or "\\" in name or ".." in p.parts or p.is_absolute():
                raise SystemExit(f"Unsafe ZIP path: {name}")
        missing = [p for p in REQUIRED if p not in names]
        if missing:
            raise SystemExit(f"ZIP missing required files: {missing}")
        zip_tests = {Path(n).name for n in names if n.startswith("tests/test_") and n.endswith(".py")}
        if zip_tests != EXPECTED_TEST_FILES:
            missing_tests = sorted(EXPECTED_TEST_FILES - zip_tests)
            unexpected_tests = sorted(zip_tests - EXPECTED_TEST_FILES)
            raise SystemExit(f"ZIP test file-set invariant violated; missing={missing_tests}, unexpected={unexpected_tests}")
        test_count = len(zip_tests)
        return {
            "files": len(names),
            "tests": test_count,
            "test_files": sorted(zip_tests),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "version": (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip(),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--output", default="AI_Council_V22_1_HOTFIX119_PRODUCTION_HARDENED_FINAL.zip")
    args = parser.parse_args()
    validate_sources()
    run_production_core_harness()
    run_tests()
    if args.check_only:
        print("RELEASE_CHECK=PASS")
        return 0
    out = ROOT / args.output
    package(out)
    manifest = check_zip(out)
    verify_extracted_release(out)
    (ROOT / "RELEASE_MANIFEST.json").write_text(json.dumps({**manifest, "zip": out.name}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    digest = manifest["sha256"]
    (ROOT / f"{out.name}.sha256").write_text(f"{digest}  {out.name}\n", encoding="utf-8")
    print(json.dumps({**manifest, "zip": out.name}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
