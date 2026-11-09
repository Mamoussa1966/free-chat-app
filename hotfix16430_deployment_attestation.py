from __future__ import annotations

"""Read-only runtime attestation tying the deployed app to exact source files."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

SCHEMA = "hotfix164.30-deployment-source-attestation/v1"
REPOSITORY = "Mamoussa1966/free-chat-app"
EXPECTED_BRANCH = "gitops-v0.4-final"
SOURCE_FILES = (
    "main.py",
    "providers.py",
    "release_identity.py",
    "conversation_store.py",
    "conversation_v25_runtime.py",
    "hotfix16430_deployment_attestation.py",
    "HOTFIX164.30_DEPLOYMENT_COMMIT_GATE.py",
    "HOTFIX164.30_RELEASE_MANIFEST.json",
    ".github/workflows/hotfix164-30-deployment-commit-closure.yml",
)
_SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_source_bundle(root: Path | str | None = None) -> dict:
    """Return deterministic file hashes; incomplete bundles are explicitly unproven."""
    base = Path(root).resolve() if root is not None else Path(__file__).resolve().parent
    hashes: dict[str, str] = {}
    missing: list[str] = []
    for rel in SOURCE_FILES:
        path = base / rel
        try:
            if not path.is_file() or path.is_symlink():
                missing.append(rel)
                continue
            hashes[rel] = _sha256(path)
        except OSError:
            missing.append(rel)
    encoded = json.dumps(hashes, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    bundle_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest() if not missing and len(hashes) == len(SOURCE_FILES) else "NOT_PROVEN"
    return {
        "source_file_sha256": hashes,
        "source_bundle_sha256": bundle_hash,
        "source_bundle_complete": not missing and len(hashes) == len(SOURCE_FILES),
        "missing_source_files": sorted(set(missing)),
    }


def _commit_from_git(root: Path) -> tuple[str, str]:
    """Prefer HEAD from the actual deployment checkout; use known CI variables only as fallback."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        candidate = proc.stdout.strip().lower()
        if proc.returncode == 0 and _SHA_RE.fullmatch(candidate):
            return candidate, "git_rev_parse_HEAD"
    except (OSError, subprocess.SubprocessError):
        pass
    for name in ("STREAMLIT_GIT_COMMIT", "GIT_COMMIT_SHA", "SOURCE_VERSION", "GITHUB_SHA"):
        candidate = str(os.environ.get(name, "")).strip().lower()
        if _SHA_RE.fullmatch(candidate):
            return candidate, f"environment:{name}"
    return "NOT_AVAILABLE", "commit_metadata_unavailable"


def _linux_process_started_at_utc(
    proc_root: Path | str = Path("/proc"),
    *,
    wall_clock_seconds: float | None = None,
    clock_ticks: int | None = None,
) -> datetime | None:
    """Read this Linux process's actual start time from procfs.

    /proc/self/stat field 22 is the process start tick count since boot.
    Combining it with /proc/uptime and wall-clock time gives the process
    creation timestamp (rather than the first Streamlit script rerun or
    the time this attestation happened). Return None when procfs evidence
    is unavailable or malformed; never substitute an app/session timestamp.
    """
    root = Path(proc_root)
    try:
        stat_text = (root / "self" / "stat").read_text(encoding="ascii").strip()
        closing_paren = stat_text.rfind(")")
        if closing_paren < 0:
            return None
        # The comm field is parenthesized and may itself contain spaces.
        # After its final ')', the first token is field 3 (state); field 22
        # is therefore token index 19.
        fields = stat_text[closing_paren + 1 :].split()
        if len(fields) <= 19:
            return None
        start_ticks = int(fields[19])
        uptime_fields = (root / "uptime").read_text(encoding="ascii").split()
        uptime_seconds = float(uptime_fields[0])
        ticks_per_second = int(clock_ticks or os.sysconf("SC_CLK_TCK"))
        wall_now = float(time.time() if wall_clock_seconds is None else wall_clock_seconds)
        if start_ticks < 0 or uptime_seconds < 0 or ticks_per_second <= 0:
            return None
        started_epoch = wall_now - uptime_seconds + (start_ticks / ticks_per_second)
        if not 0 < started_epoch <= wall_now + 1:
            return None
        return datetime.fromtimestamp(started_epoch, timezone.utc)
    except (OSError, UnicodeError, ValueError, TypeError, OverflowError, KeyError):
        return None


def build_runtime_deployment_attestation(root: Path | str | None = None) -> dict:
    """Create a fresh, redacted attestation of this running source tree."""
    base = Path(root).resolve() if root is not None else Path(__file__).resolve().parent
    result = compute_source_bundle(base)
    commit, commit_source = _commit_from_git(base)
    try:
        from providers import CURRENT_HOTFIX_RELEASE_VERSION, VERSION
        release_label = str(CURRENT_HOTFIX_RELEASE_VERSION)
        provider_core = str(VERSION)
    except Exception:
        release_label = "NOT_PROVEN"
        provider_core = "NOT_PROVEN"
    complete = result["source_bundle_complete"] is True
    generated_at = datetime.now(timezone.utc)
    process_started_at = _linux_process_started_at_utc()
    process_start_available = process_started_at is not None
    return {
        "schema": SCHEMA,
        "repository": REPOSITORY,
        "expected_deployment_branch": EXPECTED_BRANCH,
        "application_release_identity": release_label,
        "provider_core_identity": provider_core,
        "generated_at_utc": generated_at.isoformat(timespec="seconds"),
        "process_id": os.getpid(),
        "process_started_at_utc": (
            process_started_at.isoformat(timespec="milliseconds").replace("+00:00", "Z")
            if process_start_available else "NOT_AVAILABLE"
        ),
        "process_started_at_source": "linux_procfs" if process_start_available else "NOT_AVAILABLE",
        "process_start_time_status": "PASS" if process_start_available else "NOT_PROVEN",
        "process_uptime_seconds_at_attestation": (
            max(0, int((generated_at - process_started_at).total_seconds()))
            if process_start_available else None
        ),
        "observed_git_commit_sha": commit,
        "observed_git_commit_source": commit_source,
        "source_bundle_sha256": result["source_bundle_sha256"],
        "source_file_sha256": result["source_file_sha256"],
        "source_bundle_complete": complete,
        "missing_source_files": result["missing_source_files"],
        "commit_binding_status": "SOURCE_BUNDLE_READY" if complete else "NOT_PROVEN",
        "read_only": True,
        "provider_api_calls_made": 0,
        "raw_payload_exported": False,
        "secrets_exported": False,
    }
