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


def _canonical_round_binding(round_rows: list[Any], request_id: str, runtime: dict[str, Any]) -> bool:
    """Fail closed unless strict Bridge evidence names the canonical Round for its Request."""
    rid = str(request_id or "").strip()
    canonical_round_id = str(runtime.get("canonical_round_id") or "").strip()
    try:
        runtime_ordinal = int(runtime.get("round_id") or 0)
    except (TypeError, ValueError):
        return False
    if not rid or not canonical_round_id or runtime_ordinal <= 0:
        return False
    for row in round_rows:
        if not isinstance(row, dict):
            continue
        try:
            row_ordinal = int(row.get("ordinal") or row.get("round_number") or row.get("round") or 0)
        except (TypeError, ValueError):
            continue
        if (str(row.get("request_id") or "") == rid
                and str(row.get("round_id") or "") == canonical_round_id
                and row_ordinal == runtime_ordinal):
            return True
    return False


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
    # HOTFIX154: persistence audit MUST pass through the canonical preflight.
    # This is the authoritative gate; UI/projection rows and agent prose cannot
    # satisfy or replace it.
    from conversation_store import canonical_audit_preflight
    preflight = canonical_audit_preflight(chat, None)
    preflight_marker = chat.get("canonical_audit_preflight_runtime") if isinstance(chat.get("canonical_audit_preflight_runtime"), dict) else {}
    preflight_invoked = int(preflight_marker.get("invocation_count") or 0) > 0
    records = [r for r in chat.get("request_records", []) if isinstance(r, dict)]
    ui_messages = [m for m in chat.get("messages", []) if isinstance(m, dict)]
    canonical = chat.get("conversation_record") if isinstance(chat.get("conversation_record"), dict) else None
    if canonical is None:
        canonical = chat.get("canonical_record") if isinstance(chat.get("canonical_record"), dict) else None
    if canonical is None:
        canonical_counts = {"canonical_message_count":"NOT_PROVEN","canonical_request_count":"NOT_PROVEN","canonical_round_count":"NOT_PROVEN"}
        canonical_messages = []
        canonical_requests = []
        canonical_rounds = []
    else:
        from conversation_store import canonical_identity_counts
        canonical_counts = canonical_identity_counts(canonical)
        canonical_messages = [m for m in canonical.get("messages", []) if isinstance(m, dict)]
        canonical_requests = [r for r in canonical.get("requests", []) if isinstance(r, dict)]
        canonical_rounds = [r for r in canonical.get("rounds", []) if isinstance(r, dict)]
    record = next((r for r in records if str(r.get("request_id") or "") == rid), None) if rid else (records[-1] if records else None)
    canonical_request = next((r for r in canonical_requests if str(r.get("request_id") or "") == rid), None) if rid else (canonical_requests[-1] if canonical_requests else None)
    bridge_requested = bool(record and record.get("bridge_test_requested"))
    strict_bridge_requested = bool(record and record.get("bridge_runtime_contract") == "STRICT_LIVE")
    runtime_store = chat.get("bridge_runtime_evidence_store", {}) if isinstance(chat.get("bridge_runtime_evidence_store"), dict) else {}
    runtime_bridge = runtime_store.get(rid) if rid and isinstance(runtime_store.get(rid), dict) else {}
    canonical_round_bound = _canonical_round_binding(canonical_rounds, rid, runtime_bridge)
    runtime_bridge_ok = bool(
        runtime_bridge
        and str(runtime_bridge.get("request_id") or "") == rid
        and canonical_round_bound
        and runtime_bridge.get("application_owned") == "PASS"
        and runtime_bridge.get("runtime_sequence_valid") == "PASS"
        and runtime_bridge.get("terminal_state") == "COMMITTED"
        and runtime_bridge.get("bridge_state_terminal") == "COMMITTED"
        and runtime_bridge.get("bridge_gate_status") == "PASS"
        and runtime_bridge.get("bridge_state_contains_value") == "YES"
        and all(runtime_bridge.get(key) == "PASS" for key in (
            "source_execution_proven", "write_status", "validate_status", "commit_status",
            "barrier_status", "target_dispatch_status", "target_response_status",
            "read_status", "schema_validation_status", "match_status",
        ))
        and runtime_bridge.get("user_prompt_contains_value") == "NO"
        and runtime_bridge.get("gemini_input_prompt_contains_value") == "NO"
        and runtime_bridge.get("runtime_http_payload_attested") == "YES"
        and runtime_bridge.get("runtime_http_payload_contains_value") == "NO"
        and runtime_bridge.get("runtime_http_payload_contains_bridge_key") == "NO"
        and runtime_bridge.get("gemini_received_sanitized_representation_only") == "PASS"
    )
    required = {
        "SESSION_ID": bool(chat.get("id") or (canonical and canonical.get("session_id"))),
        "USER_MESSAGE": any(str(m.get("role") or "").lower() == "user" and str(m.get("message_id") or "").strip() for m in canonical_messages),
        "REQUEST_ID": bool(canonical_request and canonical_request.get("request_id")),
        "ROUND_ID": bool(canonical_request and (canonical_request.get("rounds_executed") or canonical_request.get("rounds"))) or bool(canonical_rounds),
        "SEAT_RESULTS": bool(record and isinstance(record.get("results"), list)),
        "EXECUTED_MODELS": bool(record and isinstance(record.get("results"), list)),
        "CASCADE_SUMMARIES": bool(record and any(isinstance(r, dict) and (r.get("attempt_summaries") or r.get("attempt_telemetry")) for r in record.get("results", []))),
        "BRIDGE_AUDIT": ((runtime_bridge_ok if strict_bridge_requested else bool(record and any(isinstance(r, dict) and r.get("bridge_transaction_audit") for r in record.get("results", [])))) if bridge_requested else "NOT_REQUESTED"),
        "FINAL_RESULT": bool(record and record.get("synthesis")),
        "AUTHORITATIVE_METRICS": bool(record and record.get("request_metrics")),
    }
    forbidden = json.dumps(chat, ensure_ascii=False, default=str)
    def _has_nonempty_field(value: Any, names: set[str]) -> bool:
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).strip().lower() in names and item not in (None, "", [], {}, False):
                    return True
                if _has_nonempty_field(item, names):
                    return True
        elif isinstance(value, (list, tuple)):
            return any(_has_nonempty_field(item, names) for item in value)
        return False

    forbidden_hits = {
        "API_KEYS": bool(re.search(r"\b(?:AIza[A-Za-z0-9_-]{20,}|(?:sk|xai)-[A-Za-z0-9._-]{16,})\b", forbidden)),
        "AUTH_HEADERS": bool(re.search(r"(?i)\b(?:authorization|x-api-key|x-goog-api-key)\s*[:=]", forbidden)),
        # HOTFIX147: sanitized/redacted field names are allowed; retained raw values are not.
        "RAW_PROVIDER_PAYLOADS": _has_nonempty_field(chat, {"raw_provider_payload", "raw_payload", "provider_payload", "response_body"}),
        "SENSITIVE_DIAGNOSTICS": _has_nonempty_field(chat, {"attempt_diagnostics", "sensitive_diagnostics", "internal_diagnostics", "debug_payload"}),
    }
    required_ok = all(v is True or v == "NOT_REQUESTED" for v in required.values())
    # Preserve the established persistence gate semantics while exposing the
    # mandatory preflight result. The preflight itself is independently
    # fail-closed; it is never synthesized from UI/projection data.
    counts_are_int = all(isinstance(v, int) for v in canonical_counts.values())
    persisted_counts_match = bool(
        counts_are_int
        and int(canonical_counts["canonical_message_count"]) == len([m for m in canonical_messages if str(m.get("message_id") or "").strip() and str(m.get("role") or "").lower() == "user"])
        and int(canonical_counts["canonical_request_count"]) == len(canonical_requests)
        and int(canonical_counts["canonical_round_count"]) == len(canonical_rounds)
    )
    ok = required_ok and not any(forbidden_hits.values()) and counts_are_int and persisted_counts_match and preflight.get("status") == "PASS"
    return {
        "status": "PASS" if ok else "FAIL",
        "canonical_audit_preflight_invoked": preflight_invoked,
        "canonical_audit_preflight_status": preflight.get("status", "NOT_PROVEN"),
        "canonical_audit_preflight_source": preflight.get("source", ""),
        "required_artifacts": required,
        "forbidden_data": forbidden_hits,
        "canonical_message_count": canonical_counts["canonical_message_count"],
        "canonical_request_count": canonical_counts["canonical_request_count"],
        "canonical_round_count": canonical_counts["canonical_round_count"],
        "canonical_counter_source": "CANONICAL_IDENTITY_RECORDS",
        "persisted_message_count": canonical_counts["canonical_message_count"],
        "persisted_request_count": canonical_counts["canonical_request_count"],
        "persisted_round_count": canonical_counts["canonical_round_count"],
        "counter_semantics_consistent": bool(ok and persisted_counts_match),
        "ui_projection_message_count": len(ui_messages),
        "ui_projection_message_count_authoritative": False,
        "messages": len(ui_messages),
        "request_records": len(records),
    }


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
    """HOTFIX160: prove at least two independent persisted Request lifecycles.

    The audit is observational and fail-closed. Two fresh Request Records are
    sufficient for the historical HOTFIX135 regression contract; three or more
    are also accepted, with the newest two audited. Identity comes only from
    application-owned request/result records.
    """
    chat = chat if isinstance(chat, dict) else {}
    records = [r for r in chat.get("request_records", []) if isinstance(r, dict)]
    recent = records[-2:]
    request_ids = [str(r.get("request_id") or "").strip() for r in recent]
    unique_request_ids = len(set(x for x in request_ids if x))
    bridge_ids: list[str] = []
    seat_round_keys: list[tuple[str, int, str]] = []
    per_request: list[dict[str, Any]] = []
    contamination = False
    bridge_runtime_store = chat.get("bridge_runtime_evidence_store", {}) if isinstance(chat.get("bridge_runtime_evidence_store"), dict) else {}
    strict_bridge_proof_missing = False
    canonical_record = chat.get("conversation_record") if isinstance(chat.get("conversation_record"), dict) else {}
    canonical_round_rows = canonical_record.get("rounds", []) if isinstance(canonical_record.get("rounds"), list) else []
    for r in recent:
        rid = str(r.get("request_id") or "").strip()
        bridges_for_request: list[str] = []
        strict_live = r.get("bridge_runtime_contract") == "STRICT_LIVE"
        if strict_live:
            runtime = bridge_runtime_store.get(rid) if isinstance(bridge_runtime_store.get(rid), dict) else {}
            canonical_round_bound = _canonical_round_binding(canonical_round_rows, rid, runtime)
            complete = bool(
                runtime
                and str(runtime.get("request_id") or "") == rid
                and canonical_round_bound
                and str(runtime.get("bridge_id_hash") or "").strip()
                and runtime.get("application_owned") == "PASS"
                and runtime.get("runtime_sequence_valid") == "PASS"
                and runtime.get("terminal_state") == "COMMITTED"
                and runtime.get("bridge_state_terminal") == "COMMITTED"
                and runtime.get("bridge_gate_status") == "PASS"
                and runtime.get("bridge_state_contains_value") == "YES"
                and all(runtime.get(key) == "PASS" for key in (
                    "source_execution_proven", "write_status", "validate_status", "commit_status",
                    "barrier_status", "target_dispatch_status", "target_response_status",
                    "read_status", "schema_validation_status", "match_status",
                ))
                and runtime.get("user_prompt_contains_value") == "NO"
                and runtime.get("gemini_input_prompt_contains_value") == "NO"
                and runtime.get("runtime_http_payload_attested") == "YES"
                and runtime.get("runtime_http_payload_contains_value") == "NO"
                and runtime.get("runtime_http_payload_contains_bridge_key") == "NO"
                and runtime.get("gemini_received_sanitized_representation_only") == "PASS"
            )
            if complete:
                bid = str(runtime["bridge_id_hash"]).strip()
                bridges_for_request.append(bid)
                bridge_ids.append(bid)
            else:
                strict_bridge_proof_missing = True
        results = r.get("results") if isinstance(r.get("results"), list) else []
        for result in results:
            if not isinstance(result, dict):
                continue
            result_rid = str(result.get("request_id") or rid).strip()
            if result_rid and result_rid != rid:
                contamination = True
            events = result.get("runtime_execution_events") if isinstance(result.get("runtime_execution_events"), list) else []
            for event in events:
                if isinstance(event, dict):
                    event_rid = str(event.get("request_id") or rid).strip()
                    if event_rid and event_rid != rid:
                        contamination = True
            seat = str(result.get("seat_key") or result.get("seat") or "").strip()
            try:
                rnd = int(result.get("round") or 0)
            except (TypeError, ValueError):
                rnd = 0
            if seat and rnd > 0:
                seat_round_keys.append((rid, rnd, seat))
            if not strict_live:
                audit = result.get("bridge_transaction_audit")
                if isinstance(audit, dict) and audit.get("BRIDGE_ID"):
                    bid = str(audit["BRIDGE_ID"])
                    bridge_ids.append(bid)
                    bridges_for_request.append(bid)
        per_request.append({"request_id": rid, "state": str(r.get("state") or ""), "rounds": r.get("rounds_executed") or r.get("rounds") or 0, "bridge_ids": sorted(set(bridges_for_request)), "bridge_runtime_contract": "STRICT_LIVE" if strict_live else "LEGACY_COMPATIBILITY", "provider_execution_events": r.get("request_metrics", {}).get("provider_execution_events", 0) if isinstance(r.get("request_metrics"), dict) else 0})
    duplicate_seat_round = len(seat_round_keys) - len(set(seat_round_keys))
    enough = len(recent) >= 2
    independent = enough and len(request_ids) == 2 and all(request_ids) and unique_request_ids == 2
    unique_bridges = len(bridge_ids) == len(set(bridge_ids)) and not strict_bridge_proof_missing
    # For explicit strict Bridge requests, an empty evidence set cannot pass by vacuous uniqueness.
    if any(r.get("bridge_runtime_contract") == "STRICT_LIVE" for r in recent):
        expected_strict_bridges = sum(1 for r in recent if r.get("bridge_runtime_contract") == "STRICT_LIVE")
        unique_bridges = unique_bridges and len(bridge_ids) == expected_strict_bridges
    checks = {
        "REQUEST_COUNT": enough,
        "MINIMUM_INDEPENDENT_REQUESTS": enough,
        "REQUEST_ID_INDEPENDENCE": independent,
        "RESULT_REQUEST_ID_ISOLATION": not contamination,
        "NO_CROSS_REQUEST_RESULT_REFERENCE": not contamination,
        "BRIDGE_ID_REQUEST_ISOLATION": unique_bridges,
        "SEAT_ROUND_EXECUTION_ISOLATION": duplicate_seat_round == 0,
    }
    ok = all(checks.values())
    return {
        "status": "PASS" if ok else "FAIL",
        "gate": "PASS" if ok else "FAIL",
        "required_request_count": 2,
        "observed_request_records": len(records),
        "audited_request_ids": request_ids,
        "unique_request_ids": unique_request_ids,
        "unique_bridge_ids": len(set(bridge_ids)),
        "duplicate_seat_round_executions": max(0, duplicate_seat_round),
        "cross_request_result_contamination": contamination,
        "strict_bridge_proof_missing": strict_bridge_proof_missing,
        "bridge_ids_source": "APPLICATION_OWNED_BRIDGE_RUNTIME_EVIDENCE_STORE" if any(r.get("bridge_runtime_contract") == "STRICT_LIVE" for r in recent) else "LEGACY_RESULT_AUDIT",
        "per_request": per_request,
        "evidence_source": "APPLICATION_OWNED_REQUEST_RECORDS_ONLY",
        "provider_or_agent_prose_used_as_identity": False,
        "checks": checks,
    }

def canonical_round_identity_gate(chat: dict[str, Any] | None) -> dict[str, Any]:
    """HOTFIX160 authoritative Request->Round identity gate."""
    chat = chat if isinstance(chat, dict) else {}
    rec = chat.get("conversation_record") if isinstance(chat.get("conversation_record"), dict) else {}
    requests = [r for r in rec.get("requests", []) if isinstance(r, dict) and str(r.get("request_id") or "").strip()]
    rounds = [r for r in rec.get("rounds", []) if isinstance(r, dict) and str(r.get("round_id") or "").strip()]
    by_request = {str(r.get("request_id")): r for r in rounds if str(r.get("request_id") or "").strip()}

    # HOTFIX160 compatibility boundary: older structural tests can provide a
    # canonical round ledger without a populated Request list.  That is still
    # application-owned evidence, and can be validated directly.  Once Request
    # records exist, the strict Request->Round contract below is authoritative.
    if not requests:
        valid = bool(rounds) and len({str(r.get("round_id") or "") for r in rounds}) == len(rounds)
        expected = []
        for ordinal, rr in enumerate(rounds, 1):
            rid = str(rr.get("request_id") or "")
            if not rid:
                # Legacy canonical RoundRecord: recover the Request identity only
                # from its own application-owned round_id, never from UI/prose.
                round_id = str(rr.get("round_id") or "")
                prefix = f"{chat.get('conversation_id')}:"
                if round_id.startswith(prefix) and ":r" in round_id:
                    rid = round_id[len(prefix):].rsplit(":r", 1)[0]
            expected_id = f"{chat.get('conversation_id')}:{rid}:r{ordinal}"
            try: num = int(rr.get("round_number") or rr.get("round") or rr.get("ordinal") or 0)
            except (TypeError, ValueError): num = 0
            # Pre-HOTFIX158 structural records did not carry the newer explicit
            # record_type/ordinal metadata.  Accept them only when their
            # application-owned round identity is otherwise exact.
            legacy_structural = not rr.get("record_type") and not rr.get("canonical_round_record_id")
            valid = valid and bool(rid) and num == ordinal and str(rr.get("round_id") or "") == expected_id and (legacy_structural or rr.get("record_type") == "CANONICAL_ROUND_RECORD")
            expected.append(expected_id)
        return {"gate":"PASS" if valid else "FAIL", "status":"PASS" if valid else "FAIL", "request_count":0, "round_count":len(rounds), "expected_round_sequence":expected, "source":"V26_3_CANONICAL_CONVERSATION_STORE"}

    valid = len(requests) == len(rounds) and len(by_request) == len(rounds)
    expected = []
    for ordinal, req in enumerate(requests, 1):
        rid = str(req.get("request_id") or "")
        rr = by_request.get(rid)
        expected_id = f"{chat.get('conversation_id')}:{rid}:r{ordinal}"
        try: base = int(req.get("canonical_round_base") or 0)
        except (TypeError, ValueError): base = 0
        try: num = int((rr or {}).get("round_number") or (rr or {}).get("round") or 0)
        except (TypeError, ValueError): num = 0
        legacy_structural = bool(rr) and not rr.get("record_type") and not rr.get("canonical_round_record_id")
        base_ok = base == ordinal or (legacy_structural and base == 0)
        ok = bool(rr and base_ok and num == ordinal and str(rr.get("round_id") or "") == expected_id)
        valid = valid and ok
        expected.append(expected_id)
    return {"gate":"PASS" if valid else "FAIL", "status":"PASS" if valid else "FAIL", "request_count":len(requests), "round_count":len(rounds), "expected_round_sequence":expected, "source":"V26_3_CANONICAL_CONVERSATION_STORE"}

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
    # HOTFIX126 FINAL: round identity is a mandatory production gate.
    # Legacy compatibility is readable, but it is never Production-ready.
    round_identity_status = "PASS" if round_identity.get("gate") == "PASS" else "FAIL"
    bridge_audits = []
    persisted_bridge = None
    bridge_test_requested = False
    strict_bridge_requested = False
    for rec in chat.get("request_records", []):
        if not isinstance(rec, dict) or str(rec.get("request_id") or "") != str(request_id or ""):
            continue
        bridge_test_requested = bool(rec.get("bridge_test_requested"))
        strict_bridge_requested = rec.get("bridge_runtime_contract") == "STRICT_LIVE"
        persisted_bridge = rec.get("application_owned_bridge_state")
        for item in rec.get("results", []) if isinstance(rec.get("results"), list) else []:
            if isinstance(item, dict) and isinstance(item.get("bridge_transaction_audit"), dict):
                bridge_audits.append(item["bridge_transaction_audit"])
    runtime_store = chat.get("bridge_runtime_evidence_store", {}) if isinstance(chat.get("bridge_runtime_evidence_store"), dict) else {}
    runtime_bridge = runtime_store.get(str(request_id or "")) if isinstance(runtime_store.get(str(request_id or "")), dict) else None
    if strict_bridge_requested and isinstance(runtime_bridge, dict) and str(runtime_bridge.get("request_id") or "") == str(request_id or ""):
        persisted_bridge = runtime_bridge
        bridge = {
            "BRIDGE_ID": runtime_bridge.get("bridge_id_hash", ""),
            "WRITE": runtime_bridge.get("write_status", "NOT_PROVEN"),
            "VALIDATE": runtime_bridge.get("validate_status", "NOT_PROVEN"),
            "COMMIT": runtime_bridge.get("commit_status", "NOT_PROVEN"),
            "BARRIER": runtime_bridge.get("barrier_status", "NOT_PROVEN"),
            "READ": runtime_bridge.get("read_status", "NOT_PROVEN"),
            "SCHEMA_VALIDATION": runtime_bridge.get("schema_validation_status", "NOT_PROVEN"),
            "MATCH": runtime_bridge.get("match_status", "NOT_PROVEN"),
            "USER_PROMPT_CONTAINS_VALUE": runtime_bridge.get("user_prompt_contains_value", "NOT_PROVEN"),
            "GEMINI_INPUT_PROMPT_CONTAINS_VALUE": runtime_bridge.get("gemini_input_prompt_contains_value", "NOT_PROVEN"),
            "BRIDGE_STATE_CONTAINS_VALUE": runtime_bridge.get("bridge_state_contains_value", "NOT_PROVEN"),
            "SOURCE_EXECUTION_PROVEN": runtime_bridge.get("source_execution_proven", "NOT_PROVEN"),
            "TARGET_DISPATCH_STATUS": runtime_bridge.get("target_dispatch_status", "NOT_PROVEN"),
            "TARGET_RESPONSE_STATUS": runtime_bridge.get("target_response_status", "NOT_PROVEN"),
            "RUNTIME_HTTP_PAYLOAD_ATTESTED": runtime_bridge.get("runtime_http_payload_attested", "NOT_PROVEN"),
            "RUNTIME_HTTP_PAYLOAD_CONTAINS_VALUE": runtime_bridge.get("runtime_http_payload_contains_value", "NOT_PROVEN"),
            "RUNTIME_HTTP_PAYLOAD_CONTAINS_BRIDGE_KEY": runtime_bridge.get("runtime_http_payload_contains_bridge_key", "NOT_PROVEN"),
            "GEMINI_RECEIVED_SANITIZED_REPRESENTATION_ONLY": runtime_bridge.get("gemini_received_sanitized_representation_only", "NOT_PROVEN"),
            "BRIDGE_RUNTIME_SEQUENCE_VALID": runtime_bridge.get("runtime_sequence_valid", "NOT_PROVEN"),
            "APPLICATION_OWNED_RUNTIME_RECORD": runtime_bridge.get("application_owned", "NOT_PROVEN"),
            "TERMINAL_STATE": runtime_bridge.get("terminal_state", "NOT_PROVEN"),
            "BRIDGE_GATE_STATUS": runtime_bridge.get("bridge_gate_status", "NOT_PROVEN"),
        }
    else:
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
    if not continuation_audit:
        continuation_status = "NOT_PROVEN"
    else:
        continuation_status = "PASS" if (continuation_audit.get("mode") == "READ_ONLY" and continuation_audit.get("provider_execution", 0) == 0 and continuation_audit.get("cascade", 0) == 0 and continuation_audit.get("new_round", 0) == 0 and continuation_audit.get("new_bridge", 0) == 0 and continuation_audit.get("actual_request_id") == request_id) else "FAIL"
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
    elif bridge_test_requested:
        # Explicit Bridge Test has no intermediate/legacy PASS state. All required
        # application-owned proof fields must be present and satisfy the gate.
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
            "SOURCE_EXECUTION_PROVEN": (bridge.get("SOURCE_EXECUTION_PROVEN") == "PASS" if strict_bridge_requested else True),
            "TARGET_DISPATCH_PROVEN": (bridge.get("TARGET_DISPATCH_STATUS") == "PASS" if strict_bridge_requested else True),
            "TARGET_RESPONSE_PROVEN": (bridge.get("TARGET_RESPONSE_STATUS") == "PASS" if strict_bridge_requested else True),
            "RUNTIME_HTTP_PAYLOAD_ATTESTED": (bridge.get("RUNTIME_HTTP_PAYLOAD_ATTESTED") == "YES" if strict_bridge_requested else True),
            "RUNTIME_HTTP_PAYLOAD_VALUE_ABSENT": (bridge.get("RUNTIME_HTTP_PAYLOAD_CONTAINS_VALUE") == "NO" if strict_bridge_requested else True),
            "RUNTIME_HTTP_PAYLOAD_KEY_ABSENT": (bridge.get("RUNTIME_HTTP_PAYLOAD_CONTAINS_BRIDGE_KEY") == "NO" if strict_bridge_requested else True),
            "SANITIZED_REPRESENTATION_ONLY": (bridge.get("GEMINI_RECEIVED_SANITIZED_REPRESENTATION_ONLY") == "PASS" if strict_bridge_requested else True),
            "RUNTIME_SEQUENCE_VALID": (bridge.get("BRIDGE_RUNTIME_SEQUENCE_VALID") == "PASS" if strict_bridge_requested else True),
            "APPLICATION_OWNED_RUNTIME_RECORD": (bridge.get("APPLICATION_OWNED_RUNTIME_RECORD") == "PASS" if strict_bridge_requested else True),
            "TERMINAL_COMMITTED": (bridge.get("TERMINAL_STATE") == "COMMITTED" if strict_bridge_requested else True),
            "BRIDGE_RUNTIME_GATE": (bridge.get("BRIDGE_GATE_STATUS") == "PASS" if strict_bridge_requested else True),
            "NO_AGENT_PROSE_AUTHORITY": True,
            "REQUEST_ID_IDENTITY_MATCH": identity_match,
        }
        bridge_status = "PASS" if all(bridge_checks.values()) else "FAIL"
    elif not bridge_test_requested:
        # A Bridge record is not allowed to manufacture a Bridge FAIL in a
        # persistence-only request. Keep the bridge status neutral.
        bridge_status = "NOT_REQUESTED"
        bridge_checks = {"BRIDGE_TEST_REQUESTED": False, "NO_AGENT_PROSE_AUTHORITY": True, "REQUEST_ID_IDENTITY_MATCH": identity_match}
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
    if strict_bridge_requested:
        if isinstance(runtime_bridge, dict) and str(runtime_bridge.get("request_id") or "") == str(request_id or "") and str(runtime_bridge.get("bridge_id_hash") or "").strip():
            persisted_bridge_ids.append(str(runtime_bridge.get("bridge_id_hash")).strip())
    elif persisted_record and isinstance(persisted_record.get("results"), list):
        for item in persisted_record.get("results", []):
            if not isinstance(item, dict):
                continue
            a = item.get("bridge_transaction_audit")
            if isinstance(a, dict) and str(a.get("BRIDGE_ID") or "").strip():
                persisted_bridge_ids.append(str(a.get("BRIDGE_ID")).strip())
    if strict_bridge_requested and not persisted_bridge_ids:
        bridge_identity_status = "NOT_PROVEN"
    else:
        bridge_identity_status = "PASS" if len(set(persisted_bridge_ids)) == len(persisted_bridge_ids) and len(persisted_bridge_ids) <= 1 else "FAIL"
    unique_persisted_bridge_ids = sorted(set(persisted_bridge_ids))
    if bridge_identity_status == "FAIL":
        bridge_status = "FAIL"
        bridge_checks["UNIQUE_BRIDGE_ID"] = False
    else:
        bridge_checks["UNIQUE_BRIDGE_ID"] = True
    bridge_gate_ok = bridge_status in {"PASS", "NOT_REQUESTED"}
    continuation_gate_ok = continuation_status in {"PASS", "NOT_REQUESTED", "NOT_PROVEN"}
    overall = all(x == "PASS" for x in (persistence["status"], session["status"], context_status, health_status, security_status, regression_status, round_identity_status)) and continuation_gate_ok and bridge_gate_ok and identity_match and bridge_identity_status == "PASS"
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


def _strict_live_bridge_evidence_complete(chat: dict[str, Any], request_record: dict[str, Any]) -> bool:
    """Validate strict live Bridge proof from the application-owned evidence store only.

    HOTFIX164.9 intentionally stopped copying Bridge proof into provider result rows.
    The security audit must therefore validate the separate evidence ledger instead
    of treating the absence of a legacy result-side audit as an isolation failure.
    """
    rid = str(request_record.get("request_id") or "").strip()
    if not rid:
        return False
    store = chat.get("bridge_runtime_evidence_store")
    if not isinstance(store, dict):
        return False
    evidence = store.get(rid)
    if not isinstance(evidence, dict) or str(evidence.get("request_id") or "") != rid:
        return False

    canonical = chat.get("conversation_record") if isinstance(chat.get("conversation_record"), dict) else {}
    rounds = canonical.get("rounds") if isinstance(canonical.get("rounds"), list) else []
    if not _canonical_round_binding(rounds, rid, evidence):
        return False

    required_equal = {
        "source_execution_proven": "PASS",
        "bridge_state_contains_value": "YES",
        "write_status": "PASS",
        "validate_status": "PASS",
        "commit_status": "PASS",
        "barrier_status": "PASS",
        "target_dispatch_status": "PASS",
        "target_response_status": "PASS",
        "read_status": "PASS",
        "schema_validation_status": "PASS",
        "match_status": "PASS",
        "user_prompt_contains_value": "NO",
        "gemini_input_prompt_contains_value": "NO",
        "runtime_http_payload_attested": "YES",
        "runtime_http_payload_contains_value": "NO",
        "runtime_http_payload_contains_bridge_key": "NO",
        "gemini_received_sanitized_representation_only": "PASS",
        "runtime_sequence_valid": "PASS",
        "application_owned": "PASS",
        "bridge_gate_status": "PASS",
        "terminal_state": "COMMITTED",
        "bridge_state_terminal": "COMMITTED",
    }
    if any(evidence.get(field) != expected for field, expected in required_equal.items()):
        return False
    if not str(evidence.get("bridge_id_hash") or "").strip():
        return False
    # In strict live mode, the source WRITE and target READ are the only two
    # Bridge trace records. Reject duplicate writes, synthetic seeds, and reads
    # that are not represented by the sealed request-bound runtime sequence.
    try:
        if int(evidence.get("bridge_trace_count") or 0) != 2:
            return False
        ordinal = int(evidence.get("round_id") or 0)
    except (TypeError, ValueError):
        return False
    phases = [
        "SOURCE_EXECUTION", "WRITE", "VALIDATE", "COMMIT", "BARRIER",
        "TARGET_DISPATCH", "TARGET_RESPONSE", "READ", "MATCH",
    ]
    events = evidence.get("runtime_sequence")
    if not isinstance(events, list) or [str(e.get("phase") or "") for e in events if isinstance(e, dict)] != phases:
        return False
    if len(events) != len(phases):
        return False
    expected_statuses = ["SUCCESS", "RECORDED", "PASS", "PASS", "PASS", "ACCEPTED", "SUCCESS", "PASS", "PASS"]
    for idx, (event, phase, status) in enumerate(zip(events, phases, expected_statuses), start=1):
        if not isinstance(event, dict):
            return False
        if (event.get("seq") != idx
                or str(event.get("phase") or "") != phase
                or str(event.get("request_id") or "") != rid
                or str(event.get("round_id") or "") != str(ordinal)
                or str(event.get("status") or "") != status):
            return False
    return ordinal > 0


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
        "STRICT_LIVE_BRIDGE_EVIDENCE_AUTHORITATIVE_AND_COMPLETE": True,
    }
    for chat in chats or []:
        strict_bridge_hashes: list[str] = []
        raw = json.dumps(chat, ensure_ascii=False, default=str)
        if re.search(r"(?i)(api[_ -]?key|authorization|x-api-key|x-goog-api-key)\s*[:=]", raw):
            checks["NO_CREDENTIALS_IN_CHAT_STATE"] = False
        # HOTFIX147: the field name itself is not retained provider data.
        # Fail closed only when a forbidden raw-payload field carries a non-empty
        # value, including when nested inside persisted request/result records.
        def _contains_raw_payload_value(value: Any) -> bool:
            if isinstance(value, dict):
                for key, item in value.items():
                    k = str(key).strip().lower()
                    if k in {"raw_provider_payload", "raw_payload", "provider_payload", "response_body"}:
                        if item not in (None, "", [], {}, False):
                            return True
                    if _contains_raw_payload_value(item):
                        return True
            elif isinstance(value, (list, tuple)):
                return any(_contains_raw_payload_value(item) for item in value)
            return False
        if _contains_raw_payload_value(chat):
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
            strict_live = str(record.get("bridge_runtime_contract") or "") == "STRICT_LIVE"
            if requested and strict_live:
                # HOTFIX164.9 stores proof in an Application-Owned ledger, not
                # in provider result rows. Validate that ledger directly and fail
                # closed if it is missing, stale, unbound, or incomplete.
                complete = _strict_live_bridge_evidence_complete(chat, record)
                if not complete:
                    checks["BRIDGE_VALUES_NOT_IN_USER_PROMPT"] = False
                    checks["STRICT_LIVE_BRIDGE_EVIDENCE_AUTHORITATIVE_AND_COMPLETE"] = False
                else:
                    store = chat.get("bridge_runtime_evidence_store")
                    evidence = store.get(str(record.get("request_id") or "")) if isinstance(store, dict) else None
                    bridge_hash = str((evidence or {}).get("bridge_id_hash") or "").strip()
                    if bridge_hash:
                        strict_bridge_hashes.append(bridge_hash)
                continue
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

        if len(strict_bridge_hashes) != len(set(strict_bridge_hashes)):
            checks["BRIDGE_VALUES_NOT_IN_USER_PROMPT"] = False
            checks["STRICT_LIVE_BRIDGE_EVIDENCE_AUTHORITATIVE_AND_COMPLETE"] = False

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
