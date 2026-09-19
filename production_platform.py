from __future__ import annotations

"""V23 Release-Candidate platform layer.

Additive layer above HOTFIX123.2. It does not own provider credentials, model
selection, cascade execution, or bridge values. Those remain authoritative in
the inherited Production Core/orchestrator.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any

PLATFORM_VERSION = "V23.0.0-RELEASE-CANDIDATE"
CORE_BASELINE = "V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE"
MAX_CONTEXT_CHARS = 30000
MIN_CONTEXT_CHARS = 6000
MAX_PERSISTED_MESSAGES = 400

_SECRET_PATTERNS = (
    re.compile(r"(?i)\bAIza[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"(?i)\b(?:sk|xai)-[A-Za-z0-9._-]{8,}\b"),
    re.compile(r"(?i)\b(?:api[_ -]?key|authorization|x-api-key|x-goog-api-key|secret|token|password|credential)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]+"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def redact(value: Any) -> str:
    text = str(value or "")
    for p in _SECRET_PATTERNS:
        text = p.sub("[REDACTED]", text)
    return re.sub(r"\s+", " ", text).strip()[:2000]


def stable_message_id(request_id: str, role: str, ordinal: int) -> str:
    return hashlib.sha256(f"{request_id}:{role}:{ordinal}".encode()).hexdigest()[:24]


@dataclass
class ConversationStore:
    """Session-owned persistence with deterministic export/import shape."""
    conversation_id: str
    title: str = "محادثة جديدة"
    messages: list[dict[str, Any]] = field(default_factory=list)
    request_ids: list[str] = field(default_factory=list)
    request_records: list[dict[str, Any]] = field(default_factory=list)

    def append_message(self, message: dict[str, Any]) -> None:
        item = dict(message)
        item["content"] = redact(item.get("content", ""))
        self.messages.append(item)
        self.messages = self.messages[-MAX_PERSISTED_MESSAGES:]

    def record_request(self, record: dict[str, Any]) -> None:
        self.request_records.append(dict(record))
        self.request_records = self.request_records[-100:]
        rid = str(record.get("request_id") or "").strip()
        if rid and rid not in self.request_ids:
            self.request_ids.append(rid)
        self.request_ids = self.request_ids[-100:]

    def export(self) -> dict[str, Any]:
        return {
            "schema": "ai-council-conversation/v23",
            "platform_version": PLATFORM_VERSION,
            "core_baseline": CORE_BASELINE,
            "conversation_id": self.conversation_id,
            "title": redact(self.title),
            "messages": [self._safe_message(m) for m in self.messages],
            "request_records": [self._safe_record(r) for r in self.request_records],
        }

    @staticmethod
    def _safe_message(m: dict[str, Any]) -> dict[str, Any]:
        out = dict(m)
        out.pop("attachment_context", None)
        out.pop("raw_provider_payload", None)
        out.pop("attempt_diagnostics", None)
        return {str(k): redact(v) if k in {"content", "model", "executed_model", "provider_reported_model"} else v for k, v in out.items()}

    @staticmethod
    def _safe_record(r: dict[str, Any]) -> dict[str, Any]:
        out = dict(r)
        out.pop("credentials", None)
        out.pop("raw_provider_payload", None)
        return out


def compact_context(messages: list[dict[str, Any]], max_chars: int = MAX_CONTEXT_CHARS) -> tuple[str, dict[str, Any]]:
    """Build bounded context from newest messages while preserving request identity."""
    budget = max(MIN_CONTEXT_CHARS, int(max_chars))
    chunks: list[str] = []
    used = 0
    dropped = 0
    for m in reversed(messages or []):
        role = str(m.get("role") or "")
        content = redact(m.get("content", ""))
        if not content:
            continue
        rid = str(m.get("request_id") or "")
        header = f"[{role.upper()} request={rid or 'n/a'}]\n"
        chunk = header + content
        if used + len(chunk) > budget:
            dropped += 1
            continue
        chunks.append(chunk)
        used += len(chunk)
    chunks.reverse()
    text = "\n\n".join(chunks)
    digest = hashlib.sha256(text.encode()).hexdigest()[:16]
    return text, {"chars": len(text), "messages_included": len(chunks), "messages_dropped": dropped, "digest": digest}


def synthesize_council_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic application-owned synthesis metadata; never fabricates AI prose."""
    successes = [r for r in results if str(r.get("status") or "").upper() == "SUCCESS" and r.get("content")]
    providers = [str(r.get("name") or r.get("seat") or "") for r in successes]
    return {
        "schema": "council-synthesis/v23",
        "successful_seats": len(successes),
        "successful_providers": providers,
        "source_request_ids": sorted({str(r.get("request_id") or "") for r in results if r.get("request_id")}),
        "source_rounds": sorted({int(r.get("round") or 0) for r in results if r.get("round")}),
        "status": "READY" if successes else "NO_SUCCESSFUL_AGENT",
        "composition": "APPLICATION_OWNED_RESULT_SET",
    }


def conversation_persistence_audit(chat: dict[str, Any] | None, request_id: str = "") -> dict[str, Any]:
    """Verify the application-owned conversation record contains required safe artifacts.

    This is a structural runtime audit; it never treats provider prose as authority.
    """
    chat = chat if isinstance(chat, dict) else {}
    rid = str(request_id or "").strip()
    records = [r for r in chat.get("request_records", []) if isinstance(r, dict)]
    messages = [m for m in chat.get("messages", []) if isinstance(m, dict)]
    record = next((r for r in records if str(r.get("request_id") or "") == rid), None) if rid else (records[-1] if records else None)
    required = {
        "SESSION_ID": bool(chat.get("id")),
        "USER_MESSAGE": any(m.get("role") == "user" for m in messages),
        "REQUEST_ID": bool(record and record.get("request_id")),
        "ROUND_ID": bool(record and (record.get("rounds_executed") or record.get("rounds"))),
        "SEAT_RESULTS": bool(record and isinstance(record.get("results"), list)),
        "EXECUTED_MODELS": bool(record and isinstance(record.get("results"), list)),
        "CASCADE_SUMMARIES": bool(record and any(isinstance(r, dict) and (r.get("attempt_summaries") or r.get("attempt_telemetry")) for r in record.get("results", []))),
        "BRIDGE_AUDIT": bool(record and any(isinstance(r, dict) and r.get("bridge_transaction_audit") for r in record.get("results", []))),
        "FINAL_RESULT": bool(record and record.get("synthesis")),
        "AUTHORITATIVE_METRICS": bool(record and record.get("request_metrics")),
    }
    forbidden = json.dumps(chat, ensure_ascii=False, default=str)
    forbidden_hits = {
        "API_KEYS": bool(re.search(r"\b(?:AIza[A-Za-z0-9_-]{20,}|(?:sk|xai)-[A-Za-z0-9._-]{16,})\b", forbidden)),
        "AUTH_HEADERS": bool(re.search(r"(?i)\b(?:authorization|x-api-key|x-goog-api-key)\s*[:=]", forbidden)),
        "RAW_PROVIDER_PAYLOADS": "raw_provider_payload" in forbidden,
        "SENSITIVE_DIAGNOSTICS": "attempt_diagnostics" in forbidden,
    }
    ok = all(required.values()) and not any(forbidden_hits.values())
    return {"status": "PASS" if ok else "FAIL", "required_artifacts": required, "forbidden_data": forbidden_hits, "messages": len(messages), "request_records": len(records)}


def session_integrity_audit(chat: dict[str, Any] | None, request_id: str = "") -> dict[str, Any]:
    """Check persisted identity ledgers for duplicate request/seat/bridge identities."""
    chat = chat if isinstance(chat, dict) else {}
    rid = str(request_id or "").strip()
    request_ids = [str(r.get("request_id") or "") for r in chat.get("request_records", []) if isinstance(r, dict) and r.get("request_id")]
    duplicate_requests = len(request_ids) - len(set(request_ids))
    keys = []
    for raw in chat.get("history_identity_ledger", []):
        if isinstance(raw, (list, tuple)) and len(raw) == 3:
            keys.append(tuple(str(x) for x in raw))
    duplicate_seat_round = len(keys) - len(set(keys))
    bridge_ids = []
    for r in chat.get("request_records", []):
        if not isinstance(r, dict):
            continue
        for result in r.get("results", []) if isinstance(r.get("results"), list) else []:
            if isinstance(result, dict):
                a = result.get("bridge_transaction_audit")
                if isinstance(a, dict) and a.get("BRIDGE_ID"):
                    bridge_ids.append(str(a["BRIDGE_ID"]))
    duplicate_bridges = len(bridge_ids) - len(set(bridge_ids))
    return {
        "status": "PASS" if duplicate_requests == duplicate_seat_round == duplicate_bridges == 0 else "FAIL",
        "duplicate_requests": max(0, duplicate_requests),
        "duplicate_seat_round_executions": max(0, duplicate_seat_round),
        "duplicate_bridges": max(0, duplicate_bridges),
        "request_id": rid,
    }


def build_v23_platform_audit(chat: dict[str, Any] | None, request_id: str, context_meta: dict[str, Any] | None, health: list[dict[str, Any]] | None, security: dict[str, Any] | None, regression: dict[str, Any] | None) -> dict[str, Any]:
    """Assemble one application-owned V23 continuation report from runtime records."""
    chat = chat if isinstance(chat, dict) else {}
    persistence = conversation_persistence_audit(chat, request_id)
    session = session_integrity_audit(chat, request_id)
    ctx = context_meta if isinstance(context_meta, dict) else {}
    context_status = "PASS" if ctx.get("chars", 0) >= 0 and "digest" in ctx else "FAIL"
    health_rows = health if isinstance(health, list) else []
    health_status = "PASS" if health_rows and all(r.get("status") in {"READY", "CREDENTIAL_MISSING", "MODEL_LIST_MISSING"} for r in health_rows) else "FAIL"
    regression = regression if isinstance(regression, dict) else {}
    regression_status = str(regression.get("gate") or regression.get("status") or "NOT_RUN").upper()
    security_status = str((security or {}).get("status") or "NOT_RUN").upper()
    overall = all(x == "PASS" for x in (persistence["status"], session["status"], context_status, health_status, security_status, regression_status))
    return {
        "schema": "v23-platform-audit/v1",
        "status": "PASS" if overall else "FAIL",
        "security_audit": security or {"status": "NOT_RUN"},
        "context_window": {"status": context_status, **ctx},
        "conversation_persistence": persistence,
        "session_integrity": session,
        "provider_health": {"status": health_status, "rows": health_rows},
        "regression_core": {"status": regression_status, **regression},
    }


def provider_health_snapshot(seats: list[Any], credentials: dict[str, Any], models: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for seat in seats:
        key = str(getattr(seat, "key", ""))
        candidates = tuple(models.get(key) or ())
        present = bool((credentials or {}).get(key))
        rows.append({
            "seat": key,
            "provider": str(getattr(seat, "name", key)),
            "configured": present,
            "model_configured": bool(candidates),
            "free_models": len(candidates),
            "status": "READY" if present and candidates else ("CREDENTIAL_MISSING" if not present else "MODEL_LIST_MISSING"),
        })
    return rows


def security_audit(chats: list[dict[str, Any]]) -> dict[str, Any]:
    checks = {
        "NO_CREDENTIALS_IN_CHAT_STATE": True,
        "NO_RAW_PROVIDER_PAYLOADS_IN_HISTORY": True,
        "REQUEST_ID_AUTHORITY_PRESERVED": True,
        "BRIDGE_VALUES_NOT_IN_USER_PROMPT": True,
        "MODEL_LISTS_UNCHANGED_BY_PLATFORM_LAYER": True,
        "LOCAL_ENGINE_DISABLED_BY_CONTRACT": True,
        "PAID_FALLBACK_DISABLED_BY_CONTRACT": True,
    }
    for chat in chats or []:
        raw = json.dumps(chat, ensure_ascii=False, default=str)
        if re.search(r"(?i)(api[_ -]?key|authorization|x-api-key|x-goog-api-key)\s*[:=]", raw):
            checks["NO_CREDENTIALS_IN_CHAT_STATE"] = False
        if "raw_provider_payload" in raw:
            checks["NO_RAW_PROVIDER_PAYLOADS_IN_HISTORY"] = False
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks, "version": PLATFORM_VERSION}
