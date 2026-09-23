from __future__ import annotations

"""HOTFIX123 deployed-release identity gate.

This module does not infer a release from filenames or agent prose. It records the
three runtime version layers already present in the application and exposes one
stable composite identity for deployment verification.
"""

from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parent
VERSION_FILE = (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip()

# Observed application layers at the time the Bridge/Security failure was reported.
OBSERVED_DEPLOYED_IDENTITY = {
    "provider_core": "V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE",
    "hotfix_release": "V23.0-HOTFIX144-PROSE-RUNTIME-TRUTH-SEPARATION-AUTHORITATIVE-GATE",
    "platform_release": "V24.0-HOTFIX145-CONVERSATION-RUNTIME-PROFESSIONAL-CHAT-FOUNDATION",
}

SOURCE_RELEASE_IDENTITY = {
    "VERSION.txt": VERSION_FILE,
    **OBSERVED_DEPLOYED_IDENTITY,
}

def release_fingerprint(identity: dict | None = None) -> str:
    payload = json.dumps(identity or SOURCE_RELEASE_IDENTITY, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

DEPLOYED_RELEASE_FINGERPRINT = release_fingerprint(OBSERVED_DEPLOYED_IDENTITY)
SOURCE_TREE_FINGERPRINT = release_fingerprint(SOURCE_RELEASE_IDENTITY)


def deployed_release_identity() -> dict:
    # Runtime values are read from the same application modules that render the
    # deployment identity. No agent output, UI prose, or filename is trusted.
    try:
        from providers import VERSION as provider_core, HOTFIX_RELEASE_VERSION, PLATFORM_RELEASE_VERSION
        from production_platform import PLATFORM_VERSION
        runtime = {
            "provider_core": str(provider_core),
            "hotfix_release": str(HOTFIX_RELEASE_VERSION),
            "platform_release": str(PLATFORM_RELEASE_VERSION),
            "platform_layer": str(PLATFORM_VERSION),
        }
    except Exception as exc:
        runtime = {"error": type(exc).__name__}
    runtime_matches = (
        runtime.get("provider_core") == VERSION_FILE and
        runtime.get("provider_core") == OBSERVED_DEPLOYED_IDENTITY["provider_core"] and
        runtime.get("hotfix_release") == OBSERVED_DEPLOYED_IDENTITY["hotfix_release"] and
        runtime.get("platform_release") == OBSERVED_DEPLOYED_IDENTITY["platform_release"]
    )
    return {
        "schema": "hotfix123-deployed-release-identity/v2",
        "status": "FROZEN_BASELINE",
        "observed": dict(OBSERVED_DEPLOYED_IDENTITY),
        "runtime": runtime,
        "source_version_file": VERSION_FILE,
        "deployed_release_fingerprint": DEPLOYED_RELEASE_FINGERPRINT,
        "source_tree_fingerprint": SOURCE_TREE_FINGERPRINT,
        "runtime_matches_frozen_identity": bool(runtime_matches),
        "identity_conflict": not bool(runtime_matches),
    }


def assert_deployed_release_identity() -> dict:
    """Return a fail-closed identity report; never mutate version metadata."""
    report = deployed_release_identity()
    report["gate"] = "PASS" if report.get("runtime_matches_frozen_identity") is True else "FAIL"
    return report
