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
REQUIRED = [
    "app.py", "main.py", "providers.py", "attachment_utils.py", "gitops_layer.py",
    "requirements.txt", "VERSION.txt", "README.md", "RELEASE_NOTES.md",
    ".gitignore", ".streamlit/secrets.toml.example"
]
IGNORED_DIRS = {".git", "__pycache__", ".pytest_cache", "dist", "build"}
EXPECTED_TEST_FILES = {
    "test_attachments.py", "test_core.py", "test_entrypoint.py",
    "test_gitops_layer.py", "test_hardening.py",
    "test_hotfix13_model_identity.py", "test_hotfix14_cascade_invariants.py",
    "test_hotfix14_error_classification.py", "test_hotfix14_request_history_identity.py",
    "test_hotfix17_fixes.py", "test_hotfix18_fixes.py", "test_hotfix19_fixes.py",
    "test_hotfix21_release_consistency.py", "test_hotfix21_ui_privacy.py",
    "test_provider_runtime.py", "test_v213_hardening.py", "test_v214_voice.py",
    "test_v215_resilience.py", "test_v216_hardening.py",
}
EXPECTED_TEST_FILE_COUNT = len(EXPECTED_TEST_FILES)


def validate_sources() -> None:
    missing = [p for p in REQUIRED if not (ROOT / p).is_file()]
    if missing:
        raise SystemExit(f"Missing required release files: {missing}")
    test_files = sorted(p for p in (ROOT / "tests").glob("test_*.py") if p.is_file())
    actual_test_files = {p.name for p in test_files}
    if actual_test_files != EXPECTED_TEST_FILES:
        missing = sorted(EXPECTED_TEST_FILES - actual_test_files)
        unexpected = sorted(actual_test_files - EXPECTED_TEST_FILES)
        raise SystemExit(f"Test file-set invariant violated; missing={missing}, unexpected={unexpected}")
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


def run_tests() -> None:
    """Compile and run the complete suite only inside a fresh temporary copy."""
    with tempfile.TemporaryDirectory(prefix="ai_council_release_test_") as tmp:
        sandbox = Path(tmp) / "project"
        _copy_tree_safely(sandbox)
        env = _scrub_environment()
        env["PYTHONPATH"] = str(sandbox)
        py_files = [str(sandbox / p) for p in ("app.py", "main.py", "providers.py", "attachment_utils.py", "gitops_layer.py", "build_release.py")]
        subprocess.run([sys.executable, "-m", "py_compile", *py_files], cwd=sandbox, env=env, check=True)
        subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=sandbox, env=env, check=True)


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
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "version": (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip(),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--output", default="AI_Council_V22_1_FINAL_EXACT_NAMES_UPDATED_HOTFIX24_FINAL.zip")
    args = parser.parse_args()
    validate_sources()
    run_tests()
    if args.check_only:
        print("RELEASE_CHECK=PASS")
        return 0
    out = ROOT / args.output
    package(out)
    manifest = check_zip(out)
    (ROOT / "RELEASE_MANIFEST.json").write_text(json.dumps({**manifest, "zip": out.name}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    digest = manifest["sha256"]
    (ROOT / f"{out.name}.sha256").write_text(f"{digest}  {out.name}\n", encoding="utf-8")
    print(json.dumps({**manifest, "zip": out.name}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
