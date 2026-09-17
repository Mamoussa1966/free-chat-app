from __future__ import annotations

"""HOTFIX99 Production Core Test Harness.

This is an offline, deterministic executor for the Production Core gate.
It is intentionally independent from provider APIs and never needs secrets.
It can be invoked from a real Python environment/CI with:

    python production_core_harness.py

or:

    python -m production_core_harness

The harness runs the complete pytest suite, checks previous-release file preservation,
and executes deterministic core-contract probes. AI agents are not involved in
executing the tests.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any

from production_core import (
    FreeCascadeController,
    ProviderExecutionContract,
    RequestLifecycle,
    RequestState,
    SharedContextStateMachine,
    TransactionBridgeGuard,
    TimeoutRetryPolicy,
    sanitize_audit_value,
)

def _discover_root() -> Path:
    """Locate the actual application tree, even when Streamlit launches from a parent workspace.

    Streamlit Cloud can place the repository under a parent checkout directory that also
    contains legacy test files.  The Production Core must test the application tree that
    owns this harness, not unrelated sibling/parent files.
    """
    required = {"production_core.py", "providers.py", "main.py", "VERSION.txt", "BASELINE_FILE_MANIFEST.json"}
    here = Path(__file__).absolute().parent
    if required.issubset({p.name for p in here.iterdir() if p.is_file()}):
        return here
    # If the harness was exposed from a workspace root, prefer a direct child that
    # contains the complete application contract.
    candidates = []
    for child in here.iterdir():
        if not child.is_dir() or child.name.startswith("."):
            continue
        try:
            names = {p.name for p in child.iterdir() if p.is_file()}
        except OSError:
            continue
        if required.issubset(names):
            candidates.append(child)
    if len(candidates) == 1:
        return candidates[0]
    # Finally inspect parents without resolving symlinks; this preserves the path
    # through which Streamlit exposed the application.
    for parent in (here, *here.parents):
        try:
            names = {p.name for p in parent.iterdir() if p.is_file()}
        except OSError:
            continue
        if required.issubset(names):
            return parent
    raise RuntimeError("PRODUCTION_CORE_PROJECT_ROOT_NOT_FOUND")


ROOT = _discover_root()
BASELINE = ROOT / "BASELINE_FILE_MANIFEST.json"
IGNORED = {".git", "__pycache__", ".pytest_cache", "build", "dist"}


class GateFailure(RuntimeError):
    pass


def project_files() -> set[str]:
    result = set()
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(part in IGNORED for part in rel.parts):
            continue
        if rel.suffix in {".pyc", ".zip", ".sha256"}:
            continue
        if rel.name == "RELEASE_MANIFEST.json":
            continue
        result.add(rel.as_posix())
    return result


def check_file_preservation() -> dict[str, Any]:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    expected = set(baseline["files"])
    current = project_files()
    missing = sorted(expected - current)
    added = sorted(current - expected)
    return {
        "passed": not missing,
        "baseline_files": len(expected),
        "current_files": len(current),
        "missing": missing,
        "added": added,
    }


def _pytest_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in list(env):
        upper = key.upper()
        if any(marker in upper for marker in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH")):
            env.pop(key, None)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(ROOT)
    return env


def run_pytest() -> dict[str, Any]:
    started = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests", "--tb=short", "-rA"],
        cwd=ROOT,
        env=_pytest_env(),
        text=True,
        capture_output=True,
    )
    return {
        "passed": proc.returncode == 0,
        "returncode": proc.returncode,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def run_core_probes() -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}

    def probe(name: str, fn) -> None:
        try:
            fn()
            results[name] = {"passed": True}
        except Exception as exc:
            results[name] = {"passed": False, "error": f"{type(exc).__name__}: {exc}"}

    def lifecycle():
        life = RequestLifecycle.begin("REQ-H93-0001")
        assert life.state is RequestState.RUNNING
        life.start_round(1)
        life.finish_round(1, 1, 1)
        life.finish(True)
        assert life.state is RequestState.COMPLETED
        assert any(e.event_type == "REQUEST_STARTED" for e in life.audit)
        assert any(e.event_type == "REQUEST_FINISHED" for e in life.audit)

    def cascade():
        c = FreeCascadeController([f"MODEL_{i}" for i in range(1, 15)], TimeoutRetryPolicy(cascade_max_models=10))
        seen = [c.next_model() for _ in range(12)]
        assert seen[:10] == [f"MODEL_{i}" for i in range(1, 11)]
        assert seen[10:] == [None, None]
        assert FreeCascadeController.should_continue("RATE_LIMITED", True)
        assert not FreeCascadeController.should_continue("AUTHENTICATION_ERROR", True)

    def actual_model():
        good = {
            "status": "SUCCESS", "seat": "gemini", "content": "ok",
            "model": "gemini-B", "executed_model": "gemini-B",
            "provider_reported_model": "gemini-B", "attempted_models": ["gemini-A", "gemini-B"],
            "cascade_position": 2,
        }
        ProviderExecutionContract.validate_success(good, "gemini")
        bad = dict(good, model="gemini-A", executed_model="gemini-B")
        try:
            ProviderExecutionContract.validate_success(bad, "gemini")
        except ValueError:
            return
        raise AssertionError("model identity mismatch was accepted")

    def false_success():
        fake = {"status": "SUCCESS", "seat": "gemini", "content": "", "model": "m", "executed_model": "m"}
        try:
            ProviderExecutionContract.validate_success(fake, "gemini")
        except ValueError:
            return
        raise AssertionError("false success was accepted")

    def context_transaction():
        ctx = SharedContextStateMachine()
        ctx.begin_write()
        ctx.commit()
        ctx.open_barrier()
        assert ctx.state.value == "BARRIER_OPEN"
        bridge = TransactionBridgeGuard()
        bridge.stage("gemini", "claude", "BRIDGE_TEST")
        try:
            bridge.read("claude")
        except RuntimeError:
            pass
        else:
            raise AssertionError("bridge read before commit was accepted")
        bridge.commit()
        bridge.read("claude")

    def secret_redaction():
        text = "API_KEY=SECRET_A Authorization: Bearer SECRET_B x-goog-api-key=SECRET_C"
        safe = sanitize_audit_value(text)
        assert "SECRET_A" not in safe
        assert "SECRET_B" not in safe
        assert "SECRET_C" not in safe
        assert "[REDACTED]" in safe

    probe("Request Lifecycle", lifecycle)
    probe("Free Cascade #1-#10", cascade)
    probe("Actual Model Reporting", actual_model)
    probe("False Success Protection", false_success)
    probe("Context + Transaction Guard", context_transaction)
    probe("Secret Redaction", secret_redaction)
    return results


def render(report: dict[str, Any]) -> str:
    lines = ["=" * 64, "HOTFIX99 — PRODUCTION CORE TEST HARNESS", "=" * 64]
    fp = report["file_preservation"]
    lines.append(f"File Preservation: {'PASS' if fp['passed'] else 'FAIL'}")
    lines.append(f"previous-release files: {fp['baseline_files']}")
    lines.append(f"Current files: {fp['current_files']}")
    lines.append(f"Deleted previous-release files: {len(fp['missing'])}")
    if fp["missing"]:
        lines.append("Missing: " + ", ".join(fp["missing"]))
    pytest = report["pytest"]
    lines.append(f"Full pytest suite: {'PASS' if pytest['passed'] else 'FAIL'} (rc={pytest['returncode']})")
    lines.append(f"pytest duration: {pytest['duration_seconds']}s")
    for name, result in report["core_probes"].items():
        lines.append(f"{name}: {'PASS' if result['passed'] else 'FAIL'}")
        if not result["passed"]:
            lines.append(f"  ERROR: {result['error']}")
    gate = fp["passed"] and pytest["passed"] and all(x["passed"] for x in report["core_probes"].values())
    lines.extend(["-" * 64, f"PRODUCTION CORE GATE: {'PASS' if gate else 'NO-GO'}", "=" * 64])
    if not pytest["passed"]:
        lines.append("\n--- pytest stdout ---\n" + pytest["stdout"])
        if pytest["stderr"]:
            lines.append("\n--- pytest stderr ---\n" + pytest["stderr"])
    return "\n".join(lines)


def run() -> tuple[int, dict[str, Any]]:
    report = {
        "version": "V22.1-HOTFIX99-PRODUCTION-HARDENED",
        "file_preservation": check_file_preservation(),
        "pytest": run_pytest(),
        "core_probes": run_core_probes(),
    }
    gate = report["file_preservation"]["passed"] and report["pytest"]["passed"] and all(
        x["passed"] for x in report["core_probes"].values()
    )
    report["gate"] = "PASS" if gate else "NO-GO"
    print(render(report))
    return (0 if gate else 1), report


if __name__ == "__main__":
    code, _ = run()
    raise SystemExit(code)
