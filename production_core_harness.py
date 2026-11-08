from __future__ import annotations

"""HOTFIX123 Production Core Test Harness.

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
import shutil
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


def _pytest_copy_ignore(directory: str, names: list[str]) -> set[str]:
    """Exclude runtime secrets/config from the temporary, offline pytest tree."""
    current_dir = Path(directory)
    ignored: set[str] = set()
    for name in names:
        candidate = current_dir / name
        try:
            relative = candidate.relative_to(ROOT).as_posix()
        except ValueError:
            relative = candidate.name
        lowered = name.lower()
        if lowered in IGNORED:
            ignored.add(name)
            continue
        if lowered == "secrets.toml" or lowered == ".env" or lowered.startswith(".env."):
            ignored.add(name)
            continue
        # Streamlit may resolve custom global secret paths from project config.
        # Tests do not need project runtime config; isolate it with the secrets file.
        if relative == ".streamlit/config.toml":
            ignored.add(name)
            continue
        if candidate.is_symlink():
            raise GateFailure(f"Refusing to follow a symlink in the pytest sandbox: {relative}")
    return ignored


def _copy_pytest_workspace(destination: Path) -> Path:
    """Copy source/tests into a disposable tree without runtime credentials."""
    if destination.exists():
        raise GateFailure("Pytest sandbox destination already exists")
    shutil.copytree(ROOT, destination, ignore=_pytest_copy_ignore)
    # A secrets example is safe and remains available to file-contract tests;
    # an actual secrets.toml is never copied, regardless of whether it is a link.
    if (destination / ".streamlit" / "secrets.toml").exists():
        raise GateFailure("Runtime secrets unexpectedly entered the pytest sandbox")
    return destination


def _pytest_env(project_root: Path, isolated_home: Path) -> dict[str, str]:
    """Build an environment independent of deployed provider/Streamlit settings."""
    env = os.environ.copy()
    secret_markers = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH")
    application_prefixes = (
        "AI_COUNCIL_", "COUNCIL_", "OPENAI_", "GEMINI_", "GOOGLE_",
        "ANTHROPIC_", "CLAUDE_", "GROK_", "XAI_", "KIMI_", "MOONSHOT_",
        "DEEPSEEK_", "CLOUDFLARE_", "SUPABASE_", "STREAMLIT_",
    )
    for key in list(env):
        upper = key.upper()
        if any(marker in upper for marker in secret_markers):
            env.pop(key, None)
            continue
        if upper.startswith(application_prefixes) or upper in {
            "MAX_OUTPUT_TOKENS",
            "REQUEST_TIMEOUT",
            "CASCADE_MODEL_TIMEOUT_SECONDS",
            "PROVIDER_SEAT_BUDGET_SECONDS",
            "GEMINI_REQUEST_TIMEOUT_SECONDS",
        }:
            env.pop(key, None)
    isolated_home.mkdir(parents=True, exist_ok=True)
    env.update({
        "HOME": str(isolated_home),
        "USERPROFILE": str(isolated_home),
        "XDG_CONFIG_HOME": str(isolated_home / ".config"),
        "PYTHONPATH": str(project_root),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    return env


def run_pytest() -> dict[str, Any]:
    """Run pytest from a disposable, credential-free project copy.

    Streamlit exposes project/global secrets to child processes through its
    secrets.toml lookup and may export top-level secret settings as environment
    variables. Running tests from the live checkout therefore makes outcomes
    depend on deployed account configuration (timeouts, dynamic seats, model
    lists) rather than the code contract. The temporary copy removes those
    sources and is deleted after the run; the live checkout is never modified.
    """
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="ai_council_core_pytest_") as tmp:
        temporary_root = Path(tmp)
        project_root = _copy_pytest_workspace(temporary_root / "project")
        isolated_home = temporary_root / "home"
        env = _pytest_env(project_root, isolated_home)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests", "--tb=short", "-rA"],
            cwd=project_root,
            env=env,
            text=True,
            capture_output=True,
        )
    return {
        "passed": proc.returncode == 0,
        "returncode": proc.returncode,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "workspace_mode": "TEMPORARY_CREDENTIAL_FREE_COPY",
        "project_secrets_excluded": True,
        "global_secrets_home_isolated": True,
        "provider_configuration_environment_removed": True,
        "live_checkout_modified": False,
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
        bridge.barrier()
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
    lines = ["=" * 64, "HOTFIX123 — PRODUCTION CORE TEST HARNESS", "=" * 64]
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
        "version": "V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE",
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
