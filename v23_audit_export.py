"""HOTFIX151 — V23 audit export helpers.

UI-neutral helpers for producing one complete, copy-ready/downloadable audit
artifact. No provider, persistence, counter, cascade, or security semantics are
changed here.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def build_v23_audit_export(*, platform_audit=None, final_closure_audit=None,
                           security_audit=None, health_snapshot=None,
                           production_core_report=None, production_core_code=None):
    """Return a JSON-safe, complete V23 audit export payload."""
    return {
        "schema": "v23-platform-audit-export/v1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "authoritative_scope": "APPLICATION_OWNED_RUNTIME_RECORDS_ONLY",
        "platform_audit": platform_audit or {},
        "final_closure_audit": final_closure_audit or {},
        "security_audit": security_audit or {},
        "provider_health_snapshot": health_snapshot or [],
        "production_core": {
            "code": production_core_code,
            "report": production_core_report or {},
        },
    }


def serialize_v23_audit_export(payload) -> str:
    """Serialize the export deterministically for Streamlit copy/download."""
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
