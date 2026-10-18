from __future__ import annotations

"""Read-only runtime attestation tying the deployed app to exact source files."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

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
    return {
        "schema": SCHEMA,
        "repository": REPOSITORY,
        "expected_deployment_branch": EXPECTED_BRANCH,
        "application_release_identity": release_label,
        "provider_core_identity": provider_core,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
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
