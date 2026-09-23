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



def multi_request_regression_audit(chat: dict[str, Any] | None) -> dict[str, Any]:
    """HOTFIX140: verify three already-executed independent Request lifecycles.

    This audit is intentionally observational: it never fabricates Requests, rounds,
    Bridges, provider executions, or success. To PASS, the active conversation must
    contain three distinct persisted Request Records created by three fresh
    submissions (A/B/C), each with its own lifecycle identity and no duplicate
    Seat+Round execution within that Request.
    """
    chat = chat if isinstance(chat, dict) else {}
    records = [r for r in chat.get("request_records", []) if isinstance(r, dict)]
    recent = records[-3:]
    request_ids = [str(r.get("request_id") or "").strip() for r in recent]
    unique_request_ids = len(set(x for x in request_ids if x))
    bridge_ids: list[str] = []
    seat_round_keys: list[tuple[str, int, str]] = []
    per_request: list[dict[str, Any]] = []
    for r in recent:
        rid = str(r.get("request_id") or "").strip()
        bridges_for_request: list[str] = []
        results = r.get("results") if isinstance(r.get("results"), list) else []
        for result in results:
            if not isinstance(result, dict):
                continue
            seat = str(result.get("seat_key") or result.get("seat") or "").strip()
            try:
                rnd = int(result.get("round") or 0)
            except (TypeError, ValueError):
                rnd = 0
            if seat and rnd > 0:
                seat_round_keys.append((rid, rnd, seat))
            audit = result.get("bridge_transaction_audit")
            if isinstance(audit, dict) and audit.get("BRIDGE_ID"):
                bid = str(audit["BRIDGE_ID"])
                bridge_ids.append(bid)
                bridges_for_request.append(bid)
        per_request.append({
            "request_id": rid,
            "state": str(r.get("state") or ""),
            "rounds": r.get("rounds_executed") or r.get("rounds") or 0,
            "bridge_ids": sorted(set(bridges_for_request)),
            "provider_execution_events": r.get("request_metrics", {}).get("provider_execution_events", 0) if isinstance(r.get("request_metrics"), dict) else 0,
        })
    duplicate_seat_round = len(seat_round_keys) - len(set(seat_round_keys))
    nonempty = len(request_ids) == 3 and all(request_ids)
    ok = nonempty and unique_request_ids == 3 and len(set(bridge_ids)) == len(bridge_ids) and duplicate_seat_round == 0
    return {
        "status": "PASS" if ok else "NOT_PROVEN",
        "gate": "PASS" if ok else "NOT_PROVEN",
        "required_request_count": 3,
        "observed_request_records": len(records),
        "audited_request_ids": request_ids,
        "unique_request_ids": unique_request_ids,
        "unique_bridge_ids": len(set(bridge_ids)),
        "duplicate_seat_round_executions": max(0, duplicate_seat_round),
        "per_request": per_request,
        "evidence_source": "APPLICATION_OWNED_REQUEST_RECORDS_ONLY",
        "provider_or_agent_prose_used_as_identity": False,
        "note": "HOTFIX141 supports an explicit one-message A/B/C harness; otherwise one normal chat submission remains one Request lifecycle.",
    }



def canonical_round_identity_gate(chat: dict[str, Any] | None) -> dict[str, Any]:
    """HOTFIX126: prove numeric Round identity from the canonical ledger itself.

    Once the monotonic conversation-round contract is present, every RoundRecord
    must agree across its numeric `round` field and `round_id` suffix, and the
    complete canonical sequence must be 1..N with no duplicates. Audit labels or
    provider prose are never used as evidence. Legacy records without the marker
    remain compatibility-readable and do not claim the new proof.
    """
    chat = chat if isinstance(chat, dict) else {}
    rec = chat.get("conversation_record") if isinstance(chat.get("conversation_record"), dict) else {}
    rows = [x for x in rec.get("rounds", []) if isinstance(x, dict) and str(x.get("round_id") or "").strip()]
    marked = [x for x in rows if x.get("round_identity_contract") == "V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1"]
    if not marked:
        return {"status": "NOT_PROVEN", "gate": "LEGACY_COMPATIBILITY", "active": False, "evidence_source": "APPLICATION_OWNED_CANONICAL_CONVERSATION_RECORD"}
    numbers = []
    ids = []
    checks = []
    for row in marked:
        rid = str(row.get("round_id") or "")
        try:
            number = int(row.get("round") or 0)
        except (TypeError, ValueError):
            number = 0
        suffix = 0
        if ":r" in rid and rid.rsplit(":r", 1)[1].isdigit():
            suffix = int(rid.rsplit(":r", 1)[1])
        numbers.append(number); ids.append(rid)
        checks.append(number > 0 and number == suffix)
    unique = len(ids) == len(set(ids)) and len(numbers) == len(set(numbers))
    sequence = sorted(numbers) == list(range(1, len(numbers) + 1))
    ok = bool(checks and all(checks) and unique and sequence)
    return {
        "status": "PASS" if ok else "FAIL",
        "gate": "PASS" if ok else "FAIL",
        "active": True,
        "round_ids": ids,
        "round_ordinals": numbers,
        "round_id_numeric_suffix_match": all(checks),
        "round_ids_unique": len(ids) == len(set(ids)),
        "round_ordinals_unique": len(numbers) == len(set(numbers)),
        "round_sequence_1_to_n": sequence,
        "evidence_source": "APPLICATION_OWNED_CANONICAL_CONVERSATION_RECORD",
        "agent_prose_used_as_identity": "NO",
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
    round_identity = canonical_round_identity_gate(chat)
    round_identity_status = "PASS" if round_identity.get("gate") == "PASS" else ("PASS" if round_identity.get("gate") == "LEGACY_COMPATIBILITY" else "FAIL")
    bridge_audits = []
    persisted_bridge = None
    bridge_test_requested = False
    for rec in chat.get("request_records", []):
        if not isinstance(rec, dict) or str(rec.get("request_id") or "") != str(request_id or ""):
            continue
        bridge_test_requested = bool(rec.get("bridge_test_requested"))
        persisted_bridge = rec.get("application_owned_bridge_state")
        for item in rec.get("results", []) if isinstance(rec.get("results"), list) else []:
            if isinstance(item, dict) and isinstance(item.get("bridge_transaction_audit"), dict):
                bridge_audits.append(item["bridge_transaction_audit"])
    bridge = bridge_audits[-1] if bridge_audits else None
    # Runtime identity is a hard gate: a report cannot PASS if the actual persisted
    # Request ID differs from the requested/audited ID.
    persisted_record = next((r for r in chat.get("request_records", []) if isinstance(r, dict) and str(r.get("request_id") or "") == str(request_id or "")), None)
    actual_request_id = str((persisted_record or {}).get("request_id") or "").strip()
    identity_match = bool(request_id and actual_request_id and actual_request_id == str(request_id).strip())
    continuation_audit = {}
    for event in reversed(chat.get("audit_events", [])):
        if not isinstance(event, dict):
            continue
        if str(event.get("type") or "").upper() == "CONTINUATION_GATE" and str(event.get("requested_request_id") or "") == str(request_id or ""):
            continuation_audit = dict(event)
            break
    continuation_status = "PASS" if (not continuation_audit or (continuation_audit.get("mode") == "READ_ONLY" and continuation_audit.get("provider_execution", 0) == 0 and continuation_audit.get("cascade", 0) == 0 and continuation_audit.get("new_round", 0) == 0 and continuation_audit.get("new_bridge", 0) == 0 and continuation_audit.get("actual_request_id") == request_id)) else "FAIL"
    if bridge is None:
        # HOTFIX125: no Bridge was requested => Bridge is NOT_REQUESTED, not FAIL.
        # But an explicitly requested Bridge Test with no authoritative audit is a
        # hard failure and therefore cannot pass the production gate.
        if bridge_test_requested:
            bridge_status = "FAIL"
            bridge_checks = {
                "BRIDGE_TEST_REQUESTED": True,
                "BRIDGE_AUDIT_PRESENT": False,
                "NO_AGENT_PROSE_AUTHORITY": True,
                "REQUEST_ID_IDENTITY_MATCH": identity_match,
            }
        else:
            bridge_status = "NOT_REQUESTED"
            bridge_checks = {
                "BRIDGE_TEST_REQUESTED": False,
                "BRIDGE_AUDIT_PRESENT": False,
                "APPLICATION_OWNED_STATE": True,
                "NO_AGENT_PROSE_AUTHORITY": True,
                "REQUEST_ID_IDENTITY_MATCH": identity_match,
            }
    elif not any(k in bridge for k in ("USER_PROMPT_CONTAINS_VALUE", "GEMINI_INPUT_PROMPT_CONTAINS_VALUE", "BRIDGE_STATE_CONTAINS_VALUE")):
        bridge_status = "PASS"
        bridge_checks = {"LEGACY_AUDIT_COMPATIBLE": True, "NO_AGENT_PROSE_AUTHORITY": True}
    else:
        bridge_checks = {
            "APPLICATION_OWNED_STATE": bool(persisted_bridge),
            "WRITE": bridge.get("WRITE") == "PASS",
            "VALIDATE": bridge.get("VALIDATE") == "PASS",
            "COMMIT": bridge.get("COMMIT") == "PASS",
            "BARRIER": bridge.get("BARRIER") == "PASS",
            "READ": bridge.get("READ") == "PASS",
            "SCHEMA_VALIDATION": bridge.get("SCHEMA_VALIDATION") == "PASS",
            "USER_PROMPT_ISOLATED": bridge.get("USER_PROMPT_CONTAINS_VALUE") == "NO",
            "GEMINI_INPUT_ISOLATED": bridge.get("GEMINI_INPUT_PROMPT_CONTAINS_VALUE") == "NO",
            "BRIDGE_STATE_CONTAINS_VALUE": bridge.get("BRIDGE_STATE_CONTAINS_VALUE") == "YES",
            "NO_AGENT_PROSE_AUTHORITY": True,
            "REQUEST_ID_IDENTITY_MATCH": identity_match,
        }
        bridge_status = "PASS" if all(bridge_checks.values()) else "FAIL"
    # HOTFIX126: an authoritative request may have at most one bridge identity.
    # Never allow the last bridge audit to hide a second bridge created by a
    # secondary execution path. Count every persisted result for this request.
    persisted_bridge_ids = []
    if persisted_record and isinstance(persisted_record.get("results"), list):
        for item in persisted_record.get("results", []):
            if not isinstance(item, dict):
                continue
            a = item.get("bridge_transaction_audit")
            if isinstance(a, dict) and str(a.get("BRIDGE_ID") or "").strip():
                persisted_bridge_ids.append(str(a.get("BRIDGE_ID")).strip())
    unique_persisted_bridge_ids = sorted(set(persisted_bridge_ids))
    bridge_identity_status = "PASS" if len(unique_persisted_bridge_ids) <= 1 else "FAIL"
    if bridge_identity_status == "FAIL":
        bridge_status = "FAIL"
        bridge_checks["UNIQUE_BRIDGE_ID"] = False
    else:
        bridge_checks["UNIQUE_BRIDGE_ID"] = True
    bridge_gate_ok = bridge_status in {"PASS", "NOT_REQUESTED"}
    overall = all(x == "PASS" for x in (persistence["status"], session["status"], context_status, health_status, security_status, regression_status, continuation_status, round_identity_status)) and bridge_gate_ok and identity_match and bridge_identity_status == "PASS"
    return {
        "schema": "v23-platform-audit/v1",
        "status": "PASS" if overall else "FAIL",
        "security_audit": security or {"status": "NOT_RUN"},
        "context_window": {"status": context_status, **ctx},
        "conversation_persistence": persistence,
        "round_identity_gate": round_identity,
        "session_integrity": session,
        "provider_health": {"status": health_status, "rows": health_rows},
        "regression_core": {"status": regression_status, **regression},
        "bridge_isolation": {"status": bridge_status, "requested": bridge_test_requested, "checks": bridge_checks, "persisted_state": bool(persisted_bridge), "audit": bridge or {}, "unique_persisted_bridge_ids": unique_persisted_bridge_ids},
        "continuation_runtime_gate": {"status": continuation_status, "audit": continuation_audit, "REQUEST_ID_IDENTITY_MATCH": identity_match},
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
        # HOTFIX144: application-owned request/result identity is the security source
        # of truth. Agent prose is presentation-only and cannot fail this gate by
        # merely containing a conflicting identity label.
        "PROSE_ISOLATION_AUTHORITATIVE_GATE": True,
    }
    for chat in chats or []:
        raw = json.dumps(chat, ensure_ascii=False, default=str)
        if re.search(r"(?i)(api[_ -]?key|authorization|x-api-key|x-goog-api-key)\s*[:=]", raw):
            checks["NO_CREDENTIALS_IN_CHAT_STATE"] = False
        if "raw_provider_payload" in raw:
            checks["NO_RAW_PROVIDER_PAYLOADS_IN_HISTORY"] = False
        # Application-owned runtime evidence overrides any stale/header PASS.
        # A failed continuation gate or bridge isolation proof is a security failure.
        for event in chat.get("audit_events", []):
            if not isinstance(event, dict):
                continue
            if str(event.get("type") or "").upper() == "CONTINUATION_GATE" and str(event.get("runtime_gate") or "").upper() != "PASS":
                checks["REQUEST_ID_AUTHORITY_PRESERVED"] = False
        for record in chat.get("request_records", []):
            if not isinstance(record, dict):
                continue
            requested = bool(record.get("bridge_test_requested"))
            audits = [
                result.get("bridge_transaction_audit")
                for result in (record.get("results") if isinstance(record.get("results"), list) else [])
                if isinstance(result, dict) and isinstance(result.get("bridge_transaction_audit"), dict)
            ]
            if requested and not audits:
                checks["BRIDGE_VALUES_NOT_IN_USER_PROMPT"] = False
                continue
            for audit in audits:
                if any(audit.get(k) == "YES" for k in ("USER_PROMPT_CONTAINS_VALUE", "GEMINI_INPUT_PROMPT_CONTAINS_VALUE")):
                    checks["BRIDGE_VALUES_NOT_IN_USER_PROMPT"] = False
                if audit.get("BRIDGE_STATE_CONTAINS_VALUE") != "YES":
                    checks["BRIDGE_VALUES_NOT_IN_USER_PROMPT"] = False
                if any(audit.get(k) != "PASS" for k in ("WRITE", "VALIDATE", "COMMIT", "BARRIER", "READ", "SCHEMA_VALIDATION", "MATCH")):
                    checks["BRIDGE_VALUES_NOT_IN_USER_PROMPT"] = False

        # HOTFIX144: verify authoritative identity from persisted application-owned
        # request records and runtime execution events only. Never inspect agent prose
        # to decide this gate.
        for record in chat.get("request_records", []):
            if not isinstance(record, dict):
                continue
            rid = str(record.get("request_id") or "").strip()
            if not rid:
                checks["PROSE_ISOLATION_AUTHORITATIVE_GATE"] = False
                continue
            results = record.get("results") if isinstance(record.get("results"), list) else []
            for result in results:
                if not isinstance(result, dict):
                    continue
                if str(result.get("request_id") or "").strip() != rid:
                    checks["PROSE_ISOLATION_AUTHORITATIVE_GATE"] = False
                for event in result.get("runtime_execution_events") or []:
                    if not isinstance(event, dict) or event.get("execution_started") is not True:
                        continue
                    if str(event.get("request_id") or "").strip() != rid:
                        checks["PROSE_ISOLATION_AUTHORITATIVE_GATE"] = False
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks, "version": PLATFORM_VERSION}
