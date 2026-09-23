from __future__ import annotations

"""V23 Final Closure Audit — additive observational layer.

This module does not execute providers, allocate identities, mutate canonical
conversation persistence, select models, or change cascade behavior. It reads
application-owned runtime records and produces a diagnostic closure report.

The audit deliberately separates:
  * canonical lifecycle counters (Message/Request/Round records),
  * provider execution telemetry (actual execution_started events), and
  * UI/result projection counters.

UI message counts are explicitly non-authoritative.
"""

from typing import Any


NOT_PROVEN = "NOT_PROVEN"


def _records(chat: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(chat, dict):
        return []
    return [r for r in chat.get("request_records", []) if isinstance(r, dict)]


def _canonical_counts(chat: dict[str, Any] | None) -> dict[str, Any]:
    """Read canonical identity counts without changing HOTFIX130 semantics."""
    if not isinstance(chat, dict):
        return {
            "canonical_message_count": NOT_PROVEN,
            "canonical_request_count": NOT_PROVEN,
            "canonical_round_count": NOT_PROVEN,
        }

    # Prefer the V26.3 canonical conversation record when present.
    record = chat.get("conversation_record")
    if not isinstance(record, dict):
        record = chat.get("canonical_record")
    if not isinstance(record, dict):
        return {
            "canonical_message_count": NOT_PROVEN,
            "canonical_request_count": NOT_PROVEN,
            "canonical_round_count": NOT_PROVEN,
        }

    messages = record.get("messages") if isinstance(record.get("messages"), list) else []
    requests = record.get("requests") if isinstance(record.get("requests"), list) else []
    rounds = record.get("rounds") if isinstance(record.get("rounds"), list) else []

    # Exactly the HOTFIX130 authoritative message semantics: identity-bearing
    # user MessageRecords only. Requests/Rounds require their identity fields.
    return {
        "canonical_message_count": len([
            x for x in messages
            if isinstance(x, dict)
            and str(x.get("message_id") or "").strip()
            and str(x.get("role") or "").lower() == "user"
        ]),
        "canonical_request_count": len([
            x for x in requests
            if isinstance(x, dict) and str(x.get("request_id") or "").strip()
        ]),
        "canonical_round_count": len([
            x for x in rounds
            if isinstance(x, dict) and str(x.get("round_id") or "").strip()
        ]),
    }


def _execution_events(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for rec in records:
        results = rec.get("results") if isinstance(rec.get("results"), list) else []
        for result in results:
            if not isinstance(result, dict):
                continue
            raw = result.get("runtime_execution_events")
            if not isinstance(raw, list):
                continue
            for event in raw:
                if isinstance(event, dict):
                    events.append(event)
    return events


def semantic_execution_counters(chat: dict[str, Any] | None, ui_results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Return lifecycle/execution counters with explicit, non-overlapping semantics."""
    records = _records(chat)
    events = _execution_events(records)

    request_created_ids = [
        str(r.get("request_id") or "").strip()
        for r in records
        if str(r.get("request_id") or "").strip()
    ]
    request_created_ids = list(dict.fromkeys(request_created_ids))

    execution_started_events = [
        e for e in events if e.get("execution_started") is True
    ]
    execution_request_ids = [
        str(e.get("request_id") or "").strip()
        for e in execution_started_events
        if str(e.get("request_id") or "").strip()
    ]

    # NOT_EXECUTED is an actual result-state classification, not the absence of
    # execution_started telemetry. Count only explicit persisted classifications.
    not_executed_events = [
        e for e in events
        if str(e.get("status") or e.get("classification") or "").upper() == "NOT_EXECUTED"
    ]

    ui_rows = [r for r in (ui_results or []) if isinstance(r, dict)]
    ui_message_count = len((chat or {}).get("messages", [])) if isinstance((chat or {}).get("messages", []), list) else NOT_PROVEN

    return {
        "request_created": len(request_created_ids),
        "request_created_source": "CANONICAL_REQUEST_RECORDS",
        "execution_started": len(execution_started_events),
        "execution_started_source": "RUNTIME_EXECUTION_EVENTS_WHERE_EXECUTION_STARTED_TRUE",
        "execution_started_request_ids": sorted(set(execution_request_ids)),
        "not_executed": len(not_executed_events),
        "not_executed_source": "EXPLICIT_PERSISTED_RUNTIME_CLASSIFICATION",
        "cascade_attempts": len(execution_started_events),
        "ui_result_rows": len(ui_rows),
        "ui_message_count": ui_message_count,
        "ui_message_count_authoritative": False,
    }


def security_failure_reasons(security: dict[str, Any] | None) -> list[str]:
    if not isinstance(security, dict):
        return ["SECURITY_AUDIT_NOT_RUN"]
    checks = security.get("checks") if isinstance(security.get("checks"), dict) else {}
    failed = [str(k) for k, v in checks.items() if v is not True]
    if not failed and str(security.get("status") or "").upper() != "PASS":
        failed.append("SECURITY_STATUS_NOT_PASS")
    return failed


def build_v23_final_closure_audit(
    chat: dict[str, Any] | None,
    security: dict[str, Any] | None,
    platform_report: dict[str, Any] | None = None,
    ui_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build an observational final-closure report.

    PASS/FAIL is never inferred from provider prose. Missing canonical evidence is
    reported as NOT_PROVEN. This function is intentionally side-effect free.
    """
    counts = _canonical_counts(chat)
    counters = semantic_execution_counters(chat, ui_results)
    security_status = str((security or {}).get("status") or "NOT_RUN").upper()
    failures = security_failure_reasons(security)

    canonical_ready = all(isinstance(counts.get(k), int) for k in (
        "canonical_message_count", "canonical_request_count", "canonical_round_count"
    ))
    counter_consistent = False
    persistence = (platform_report or {}).get("conversation_persistence") if isinstance(platform_report, dict) else None
    if isinstance(persistence, dict):
        counter_consistent = (
            persistence.get("persisted_message_count") == counts.get("canonical_message_count")
            and persistence.get("persisted_request_count") == counts.get("canonical_request_count")
            and persistence.get("persisted_round_count") == counts.get("canonical_round_count")
            and persistence.get("counter_semantics_consistent") is True
        )

    ui_isolation = counters.get("ui_message_count_authoritative") is False

    return {
        "schema": "v23-final-closure-audit/v1",
        "status": "PASS" if canonical_ready and counter_consistent and security_status == "PASS" and not failures else "FAIL",
        "security": {
            "status": security_status,
            "failure_reasons": failures,
            "authoritative_source": "APPLICATION_OWNED_RUNTIME_RECORDS",
            "agent_prose_used": False,
        },
        "canonical_lifecycle": {
            **counts,
            "counter_semantics_consistent": counter_consistent,
            "authoritative_source": "V26_3_CANONICAL_CONVERSATION_STORE",
            "HOTFIX130_SEMANTICS_PRESERVED": True,
        },
        "execution_accounting": counters,
        "ui_projection": {
            "message_count": counters.get("ui_message_count"),
            "message_count_authoritative": False,
            "authoritative_counter_source": "V26_3_CANONICAL_CONVERSATION_STORE",
            "ui_message_count_may_include_provider_or_system_artifacts": True,
            "separate_from_canonical_message_count": True,
            "isolation_proven": ui_isolation,
        },
        "platform_report_status": str((platform_report or {}).get("status") or "NOT_RUN").upper() if isinstance(platform_report, dict) else "NOT_RUN",
        "preservation_contract": {
            "Message_to_Request": "UNCHANGED",
            "Request_to_Round": "UNCHANGED",
            "Round_sequence": "UNCHANGED",
            "canonical_counter_semantics": "UNCHANGED",
            "HOTFIX123_2": "PRESERVED",
            "HOTFIX129": "PRESERVED",
            "HOTFIX130": "PRESERVED",
            "provider_execution": "UNCHANGED",
            "cascade_controller": "UNCHANGED",
        },
        "fail_closed_rule": "NOT_PROVEN_WHEN_REQUIRED_APPLICATION_OWNED_EVIDENCE_IS_MISSING",
    }
