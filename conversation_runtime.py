from __future__ import annotations

"""HOTFIX145 Conversation Runtime.

This layer is deliberately additive. It owns conversation/session/message/round
identity and provenance metadata, but never owns provider credentials, model
selection, cascade policy, or Transactional Bridge values.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import re
from typing import Any

CONVERSATION_RUNTIME_VERSION = "V24.0-HOTFIX145-CONVERSATION-RUNTIME"
SCHEMA = "ai-council-conversation-runtime/v1"

_SECRET_PATTERNS = (
    re.compile(r"(?i)\bAIza[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"(?i)\b(?:sk|xai)-[A-Za-z0-9._-]{8,}\b"),
    re.compile(r"(?i)\b(?:api[_ -]?key|authorization|x-api-key|x-goog-api-key|secret|token|password|credential)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]+"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sanitize(value: Any, limit: int = 4000) -> str:
    text = str(value or "")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text[:limit]


def new_id(prefix: str) -> str:
    import uuid
    return f"{prefix}_{uuid.uuid4().hex}"


@dataclass(frozen=True)
class Provenance:
    conversation_id: str
    session_id: str
    message_id: str
    round_id: str
    request_id: str
    provider: str
    seat: str
    model: str
    attempt: int
    status: str
    classification: str = ""
    cascade_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "result-provenance/v1",
            "conversation_id": self.conversation_id,
            "session_id": self.session_id,
            "message_id": self.message_id,
            "round_id": self.round_id,
            "request_id": self.request_id,
            "provider": sanitize(self.provider, 120),
            "seat": sanitize(self.seat, 40),
            "model": sanitize(self.model, 200),
            "attempt": int(self.attempt or 0),
            "status": sanitize(self.status, 80),
            "classification": sanitize(self.classification, 100),
            "cascade_action": sanitize(self.cascade_action, 120),
        }


def ensure_conversation_state(chat: dict[str, Any]) -> dict[str, Any]:
    """Upgrade old chat dictionaries without replacing existing identity."""
    chat.setdefault("conversation_id", str(chat.get("id") or new_id("conv")))
    chat.setdefault("session_id", new_id("sess"))
    chat.setdefault("conversation_schema", SCHEMA)
    chat.setdefault("conversation_runtime_version", CONVERSATION_RUNTIME_VERSION)
    chat.setdefault("message_ledger", [])
    chat.setdefault("round_ledger", [])
    chat.setdefault("provenance_ledger", [])
    chat.setdefault("conversation_context", {"version": 1, "digest": "", "chars": 0, "messages_included": 0})
    return chat


def register_message(chat: dict[str, Any], message: dict[str, Any]) -> dict[str, Any]:
    ensure_conversation_state(chat)
    item = dict(message)
    mid = str(item.get("id") or new_id("msg"))
    item["id"] = mid
    item["conversation_id"] = chat["conversation_id"]
    item["session_id"] = chat["session_id"]
    item["created_at"] = item.get("created_at") or utc_now()
    chat["message_ledger"].append({
        "message_id": mid,
        "conversation_id": chat["conversation_id"],
        "session_id": chat["session_id"],
        "role": sanitize(item.get("role"), 40),
        "request_id": sanitize(item.get("request_id"), 80),
        "created_at": item["created_at"],
    })
    chat["message_ledger"] = chat["message_ledger"][-400:]
    return item


def begin_round(chat: dict[str, Any], message_id: str, request_id: str, round_no: int) -> str:
    ensure_conversation_state(chat)
    round_id = f"{chat['conversation_id']}:{request_id}:r{int(round_no)}"
    row = {
        "round_id": round_id,
        "conversation_id": chat["conversation_id"],
        "session_id": chat["session_id"],
        "message_id": str(message_id),
        "request_id": str(request_id),
        "round": int(round_no),
        "status": "STARTED",
        "created_at": utc_now(),
    }
    chat["round_ledger"].append(row)
    # V26.3.5: the canonical ConversationRecord is updated at round creation,
    # not reconstructed later by the audit.
    record = chat.setdefault("conversation_record", {})
    record.setdefault("rounds", [])
    if not any(isinstance(x, dict) and str(x.get("round_id") or "") == round_id for x in record["rounds"]):
        record["rounds"].append(dict(row))
    return round_id


def finish_round(chat: dict[str, Any], round_id: str, status: str, result_count: int) -> None:
    ensure_conversation_state(chat)
    for row in reversed(chat["round_ledger"]):
        if row.get("round_id") == round_id:
            row.update({"status": sanitize(status, 40), "result_count": int(result_count), "finished_at": utc_now()})
            record = chat.get("conversation_record") if isinstance(chat.get("conversation_record"), dict) else {}
            for canonical in record.get("rounds", []) if isinstance(record.get("rounds"), list) else []:
                if isinstance(canonical, dict) and canonical.get("round_id") == round_id:
                    canonical.update({"status": row["status"], "result_count": row["result_count"], "finished_at": row["finished_at"]})
                    break
            return


def attach_request_identity(record: dict[str, Any], chat: dict[str, Any], message_id: str, request_id: str) -> None:
    ensure_conversation_state(chat)
    record.update({
        "conversation_id": chat["conversation_id"],
        "session_id": chat["session_id"],
        "message_id": str(message_id),
        "runtime_schema": SCHEMA,
    })


def append_provenance(chat: dict[str, Any], row: dict[str, Any]) -> None:
    ensure_conversation_state(chat)
    safe = {k: row.get(k) for k in (
        "conversation_id", "session_id", "message_id", "round_id", "request_id",
        "provider", "seat", "model", "attempt", "status", "classification", "cascade_action"
    )}
    chat["provenance_ledger"].append({k: sanitize(v, 300) if isinstance(v, str) else v for k, v in safe.items()})
    chat["provenance_ledger"] = chat["provenance_ledger"][-2000:]


def update_context_meta(chat: dict[str, Any], meta: dict[str, Any], digest: str = "") -> None:
    ensure_conversation_state(chat)
    chat["conversation_context"] = {
        "version": 1,
        "digest": sanitize(digest or meta.get("digest"), 80),
        "chars": int(meta.get("chars", 0) or 0),
        "messages_included": int(meta.get("messages_included", 0) or 0),
        "messages_dropped": int(meta.get("messages_dropped", 0) or 0),
        "updated_at": utc_now(),
    }


def conversation_audit(chat: dict[str, Any] | None) -> dict[str, Any]:
    chat = chat if isinstance(chat, dict) else {}
    ensure_conversation_state(chat)
    messages = [x for x in chat.get("messages", []) if isinstance(x, dict)]
    records = [x for x in chat.get("request_records", []) if isinstance(x, dict)]
    requests = [str(x.get("request_id") or "") for x in records if x.get("request_id")]
    round_rows = [x for x in chat.get("round_ledger", []) if isinstance(x, dict)]
    round_ids = [str(x.get("round_id") or "") for x in round_rows if x.get("round_id")]
    prov = [x for x in chat.get("provenance_ledger", []) if isinstance(x, dict)]
    checks = {
        "CONVERSATION_ID_STABLE": bool(chat.get("conversation_id")) and all(x.get("conversation_id") == chat.get("conversation_id") for x in records + messages if x.get("conversation_id")),
        "SESSION_ID_STABLE": bool(chat.get("session_id")) and all(x.get("session_id") == chat.get("session_id") for x in records + messages if x.get("session_id")),
        "MESSAGE_LEDGER_PRESENT": len(messages) == 0 or len(chat.get("message_ledger", [])) >= 1,
        "REQUEST_IDS_UNIQUE": len(requests) == len(set(requests)),
        "ROUND_IDS_UNIQUE": len(round_ids) == len(set(round_ids)),
        "PROVENANCE_SAFE": not any(k in str(prov).lower() for k in ("api_key", "authorization", "x-api-key", "bearer ")),
        "NO_BRIDGE_OWNERSHIP": all("bridge" not in str(x).lower() for x in prov),
    }
    return {
        "schema": "conversation-runtime-audit/v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "conversation_id": chat.get("conversation_id"),
        "session_id": chat.get("session_id"),
        "message_count": len(messages),
        "request_count": len(requests),
        "round_count": len(round_ids),
        "provenance_count": len(prov),
        "context": dict(chat.get("conversation_context") or {}),
    }


def provenance_for_result(chat: dict[str, Any], message_id: str, round_no: int, result: dict[str, Any]) -> list[dict[str, Any]]:
    ensure_conversation_state(chat)
    request_id = str(result.get("request_id") or "")
    round_id = f"{chat['conversation_id']}:{request_id}:r{int(round_no)}"
    telemetry = result.get("attempt_telemetry") or []
    rows: list[dict[str, Any]] = []
    for item in telemetry if isinstance(telemetry, list) else []:
        if not isinstance(item, dict):
            continue
        row = Provenance(
            conversation_id=chat["conversation_id"], session_id=chat["session_id"], message_id=str(message_id),
            round_id=round_id, request_id=request_id, provider=str(result.get("name") or result.get("seat") or ""),
            seat=str(result.get("seat") or ""), model=str(item.get("model") or result.get("executed_model") or ""),
            attempt=int(item.get("attempt") or 0), status=str(item.get("status") or result.get("status") or ""),
            classification=str(item.get("classification") or ""), cascade_action=str(item.get("cascade_action") or ""),
        ).to_dict()
        append_provenance(chat, row)
        rows.append(row)
    return rows
