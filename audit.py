# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Iterable, Optional


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_audit(run_id: str, query: str, results: Iterable[object], moderator: Optional[object], app_version: str, schema_version: str) -> dict:
    rows = [asdict(r) if hasattr(r, "__dataclass_fields__") else dict(r) for r in results]
    mod = asdict(moderator) if moderator is not None and hasattr(moderator, "__dataclass_fields__") else moderator
    return {
        "schema_version": schema_version,
        "app_version": app_version,
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "query_sha256": sha256_text(query),
        "identity_policy": "Official identity is asserted only after a successful authenticated official-provider response. Local output never impersonates a commercial model.",
        "free_mode_guarantee": "No credential means no provider network call; that seat uses Local Engine directly.",
        "results": rows,
        "moderator": mod,
    }


def dumps_audit(*args, **kwargs) -> str:
    return json.dumps(build_audit(*args, **kwargs), ensure_ascii=False, indent=2)
