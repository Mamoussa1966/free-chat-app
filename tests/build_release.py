from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent
VERSION = (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip()
REQUIRED = [
    "app.py", "main.py", "providers.py", "attachment_utils.py", "requirements.txt",
    "VERSION.txt", "README.md", "RELEASE_NOTES.md", ".gitignore",
    ".streamlit/secrets.toml.example",
]


def validate_sources() -> None:
    py_files = sorted(ROOT.rglob("*.py"))
    for path in py_files:
        if "__pycache__" in path.parts:
            continue
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    missing = [p for p in REQUIRED if not (ROOT / p).is_file()]
    if missing:
        raise SystemExit(f"Missing required release files: {missing}")


def run_tests() -> None:
    compile_cmd = [sys.executable, "-m", "py_compile"] + [str(ROOT / p) for p in ("app.py", "main.py", "providers.py", "attachment_utils.py")]
    subprocess.run(compile_cmd, cwd=ROOT, check=True)
    test_cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"]
    subprocess.run(test_cmd, cwd=ROOT, check=True)


def package(output: Path) -> Path:
    files = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("__pycache__/") or "/__pycache__/" in rel or rel.endswith(".pyc") or rel.endswith(".pyo"):
            continue
        if rel.startswith("dist/") or rel.startswith(".git/"):
            continue
        # Never nest release artifacts inside a new release archive.
        if path.suffix.lower() in {".zip", ".sha256"}:
            continue
        if path.name == "RELEASE_MANIFEST.json":
            continue
        files.append((path, rel))

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path, rel in files:
            zf.write(path, rel)
    return output


def write_hash(path: Path) -> Path:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    sidecar = path.with_suffix(path.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return sidecar


def check_zip(path: Path) -> dict:
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        bad = [n for n in names if n.startswith("/") or "\\" in n or ".." in Path(n).parts]
        duplicate_names = sorted({n for n in names if names.count(n) > 1})
        if duplicate_names:
            raise SystemExit(f"ZIP contains duplicate paths: {duplicate_names}")
        if bad:
            raise SystemExit(f"Unsafe ZIP paths: {bad}")
        required_missing = [p for p in REQUIRED if p not in names]
        if required_missing:
            raise SystemExit(f"ZIP missing required files: {required_missing}")
        return {"files": len(names), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "version": VERSION}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--output", default=f"AI_Council_V22_1_FINAL_HARDENED_HOTFIX6.zip")
    args = parser.parse_args()

    validate_sources()
    run_tests()
    if args.check_only:
        print("RELEASE_CHECK=PASS")
        return 0

    out = ROOT / args.output
    package(out)
    manifest = check_zip(out)
    (ROOT / "RELEASE_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sidecar = write_hash(out)
    print(json.dumps({**manifest, "zip": out.name, "sha256_file": sidecar.name}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
