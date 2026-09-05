from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

AUDIT_FILE = os.path.join('audit', 'audit_history.jsonl')
_SECRET_PATTERNS = [
    re.compile(r'sk-[A-Za-z0-9_\-]{12,}'),
    re.compile(r'AIza[A-Za-z0-9_\-]{20,}'),
    re.compile(r'xai-[A-Za-z0-9_\-]{12,}'),
    re.compile(r'Bearer\s+[A-Za-z0-9._\-]{12,}', re.I),
]


def _safe_error(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub('[REDACTED]', text)
    return text[:120]


def log_event(seat: str, status: str, mode: str, latency: float, error_type: str | None = None) -> None:
    os.makedirs(os.path.dirname(AUDIT_FILE), exist_ok=True)
    event = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'seat': seat,
        'status': status,
        'mode': mode,
        'latency_seconds': round(float(latency), 4),
        'error_type': _safe_error(error_type),
    }
    with open(AUDIT_FILE, 'a', encoding='utf-8') as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + '\n')
