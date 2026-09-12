from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
REQUIRED = [
    "app.py", "main.py", "providers.py", "attachment_utils.py", "gitops_layer.py", "requirements.txt", "VERSION.txt", "README.md", "RELEASE_NOTES.md", ".gitignore", ".streamlit/secrets.toml.example"
]


def validate_sources() -> None:
    missing = [p for p in REQUIRED if not (ROOT / p).is_file()]
    if missing:
        raise SystemExit(f"Missing required release files: {missing}")
    for path in sorted(ROOT.rglob("*.py")):
        if any(part in {"__pycache__", ".pytest_cache", "dist", "build"} for part in path.parts):
            continue
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))
        compile(source, str(path), "exec")


def run_tests() -> None:
    py_files = [str(ROOT / p) for p in ("app.py", "main.py", "providers.py", "attachment_utils.py", "gitops_layer.py")]
    subprocess.run([sys.executable, "-m", "py_compile", *py_files], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, check=True)


def package(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT).as_posix()
            if any(part in {"__pycache__", ".pytest_cache", "dist", "build"} for part in path.relative_to(ROOT).parts):
                continue
            if rel.endswith((".pyc", ".pyo", ".zip")) or rel.endswith(".sha256") or rel == "RELEASE_MANIFEST.json":
                continue
            zf.write(path, rel)


def check_zip(path: Path) -> dict:
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        if len(names) != len(set(names)):
            raise SystemExit("Duplicate ZIP member names detected")
        for name in names:
            p = Path(name.replace("\\", "/"))
            if name.startswith("/") or ".." in p.parts:
                raise SystemExit(f"Unsafe ZIP path: {name}")
            if p.is_absolute():
                raise SystemExit(f"Absolute ZIP path: {name}")
        missing = [p for p in REQUIRED if p not in names]
        if missing:
            raise SystemExit(f"ZIP missing required files: {missing}")
        return {"files": len(names), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "version": (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--output", default="AI_Council_V22_1_FINAL_EXACT_NAMES_UPDATED_HOTFIX14_DIAGNOSTIC_HARDENED.zip")
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
