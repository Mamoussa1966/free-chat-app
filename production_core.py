from __future__ import annotations

"""Production Core.

Pure orchestration contracts.  This module contains no provider SDKs and never
accepts or stores credential values.  Provider adapters remain responsible for
official API transport; this layer enforces lifecycle, cascade, identity,
state-machine, transaction and audit invariants around them.
"""

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import re
import time
from typing import Any, Iterable, Mapping, Optional, Sequence


VERSION = "V22.1-HOTFIX94-PRODUCTION-HARDENED"
FREE_CASCADE_MAX = 10


class RequestState(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RoundState(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class SharedContextState(str, Enum):
    OPEN = "OPEN"
    PENDING = "PENDING"
    COMMITTED = "COMMITTED"
    BARRIER_OPEN = "BARRIER_OPEN"
    CLOSED = "CLOSED"


class TransactionState(str, Enum):
    IDLE = "IDLE"
    PENDING = "PENDING"
    COMMITTED = "COMMITTED"
    BARRIER_OPEN = "BARRIER_OPEN"
    REJECTED = "REJECTED"


FAILURE_CLASSES = {
    "MODEL_UNAVAILABLE", "QUOTA_EXCEEDED", "RATE_LIMITED",
    "AUTHENTICATION_ERROR", "API_ERROR", "NETWORK_ERROR", "TIMEOUT", "UNKNOWN",
}

_REDACT_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]+"),
    re.compile(r"(?i)(api[_ -]?key|authorization|x-api-key|x-goog-api-key)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)(secret|token|password|credential)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)\b(?:sk|xai)-[A-Za-z0-9._-]{8,}\b"),
    re.compile(r"(?i)\bAIza[A-Za-z0-9_-]{20,}\b"),
)


def sanitize_audit_value(value: Any) -> str:
    text = str(value or "")
    for pattern in _REDACT_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return re.sub(r"\s+", " ", text).strip()[:500]


def request_fingerprint(request_id: str) -> str:
    return hashlib.sha256(str(request_id).encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class TimeoutRetryPolicy:
    timeout_seconds: Optional[float] = None
    max_transport_retries: int = 0
    cascade_max_models: int = FREE_CASCADE_MAX

    def bounded(self) -> "TimeoutRetryPolicy":
        timeout = None if self.timeout_seconds is None else max(0.1, float(self.timeout_seconds))
        retries = max(0, int(self.max_transport_retries))
        models = max(1, min(FREE_CASCADE_MAX, int(self.cascade_max_models)))
        return TimeoutRetryPolicy(timeout, retries, models)


@dataclass
class AuditEvent:
    request_id: str
    round_id: int
    event_type: str
    provider: str = ""
    model: str = ""
    cascade_position: Optional[int] = None
    status: str = ""
    classification: str = ""
    latency_ms: Optional[float] = None
    shared_context_action: str = ""
    transaction_status: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, str] = field(default_factory=dict)

    def public(self) -> dict:
        return {
            "request_id": self.request_id,
            "request_fingerprint": request_fingerprint(self.request_id),
            "round_id": int(self.round_id),
            "event_type": sanitize_audit_value(self.event_type),
            "provider": sanitize_audit_value(self.provider),
            "model": sanitize_audit_value(self.model),
            "cascade_position": self.cascade_position,
            "status": sanitize_audit_value(self.status),
            "classification": sanitize_audit_value(self.classification),
            "latency_ms": None if self.latency_ms is None else round(float(self.latency_ms), 3),
            "shared_context_action": sanitize_audit_value(self.shared_context_action),
            "transaction_status": sanitize_audit_value(self.transaction_status),
            "timestamp": float(self.timestamp),
            "metadata": {sanitize_audit_value(k): sanitize_audit_value(v) for k, v in self.metadata.items()},
        }


class RequestLifecycle:
    _allowed = {
        RequestState.CREATED: {RequestState.RUNNING, RequestState.CANCELLED},
        RequestState.RUNNING: {RequestState.COMPLETED, RequestState.FAILED, RequestState.CANCELLED},
        RequestState.COMPLETED: set(),
        RequestState.FAILED: set(),
        RequestState.CANCELLED: set(),
    }

    def __init__(self, request_id: str):
        self.request_id = str(request_id or "").strip()
        if not self.request_id:
            raise ValueError("request_id is required")
        self.state = RequestState.CREATED
        self.started_at = time.time()
        self.rounds: dict[int, RoundState] = {}
        self.audit: list[AuditEvent] = []
        self.transition(RequestState.RUNNING, "REQUEST_STARTED")

    @classmethod
    def begin(cls, request_id: str) -> "RequestLifecycle":
        return cls(request_id)

    def transition(self, target: RequestState, event_type: str = "STATE_TRANSITION") -> None:
        target = RequestState(target)
        if target == self.state:
            return
        if target not in self._allowed[self.state]:
            raise RuntimeError(f"Invalid request transition: {self.state.value} -> {target.value}")
        self.state = target
        self.record(event_type, status=target.value)

    def start_round(self, round_id: int) -> None:
        rid = int(round_id)
        if self.state != RequestState.RUNNING:
            raise RuntimeError("Cannot start a round outside RUNNING request state")
        if rid in self.rounds:
            raise RuntimeError(f"Round already exists: {rid}")
        self.rounds[rid] = RoundState.RUNNING
        self.record("ROUND_STARTED", round_id=rid, status=RoundState.RUNNING.value)

    def finish_round(self, round_id: int, success_count: int, total_count: int) -> None:
        rid = int(round_id)
        if self.rounds.get(rid) != RoundState.RUNNING:
            raise RuntimeError(f"Round {rid} is not RUNNING")
        if int(success_count) == int(total_count) and total_count > 0:
            state = RoundState.COMPLETED
        elif int(success_count) > 0:
            state = RoundState.PARTIAL
        else:
            state = RoundState.FAILED
        self.rounds[rid] = state
        self.record("ROUND_FINISHED", round_id=rid, status=state.value,
                    metadata={"success_count": str(success_count), "total_count": str(total_count)})

    def finish(self, success: bool = True) -> None:
        self.transition(RequestState.COMPLETED if success else RequestState.FAILED,
                        "REQUEST_FINISHED" if success else "REQUEST_FAILED")

    def record(self, event_type: str, round_id: int = 0, **kwargs: Any) -> AuditEvent:
        event = AuditEvent(self.request_id, int(round_id), event_type, **kwargs)
        self.audit.append(event)
        return event

    def audit_snapshot(self) -> list[dict]:
        return [event.public() for event in self.audit]


class RoundStateMachine:
    def __init__(self, round_id: int):
        self.round_id = int(round_id)
        self.state = RoundState.CREATED

    def start(self) -> None:
        if self.state != RoundState.CREATED:
            raise RuntimeError("Round can only start once")
        self.state = RoundState.RUNNING

    def finish(self, success_count: int, total_count: int) -> RoundState:
        if self.state != RoundState.RUNNING:
            raise RuntimeError("Round must be RUNNING before finish")
        if success_count == total_count and total_count > 0:
            self.state = RoundState.COMPLETED
        elif success_count > 0:
            self.state = RoundState.PARTIAL
        else:
            self.state = RoundState.FAILED
        return self.state


class SharedContextStateMachine:
    def __init__(self):
        self.state = SharedContextState.OPEN

    def begin_write(self) -> None:
        if self.state not in {SharedContextState.OPEN, SharedContextState.COMMITTED}:
            raise RuntimeError("Shared Context cannot begin a write in current state")
        self.state = SharedContextState.PENDING

    def commit(self) -> None:
        if self.state != SharedContextState.PENDING:
            raise RuntimeError("Shared Context commit requires PENDING state")
        self.state = SharedContextState.COMMITTED

    def open_barrier(self) -> None:
        if self.state != SharedContextState.COMMITTED:
            raise RuntimeError("Shared Context barrier requires COMMITTED state")
        self.state = SharedContextState.BARRIER_OPEN

    def close(self) -> None:
        if self.state not in {SharedContextState.OPEN, SharedContextState.COMMITTED, SharedContextState.BARRIER_OPEN}:
            raise RuntimeError("Shared Context cannot close while write is pending")
        self.state = SharedContextState.CLOSED


class TransactionBridgeGuard:
    def __init__(self):
        self.state = TransactionState.IDLE
        self.source_provider = ""
        self.target_provider = ""
        self.key = ""

    def stage(self, source_provider: str, target_provider: str, key: str) -> None:
        if self.state not in {TransactionState.IDLE, TransactionState.COMMITTED}:
            raise RuntimeError("Transaction already has a pending operation")
        if not str(key).strip():
            raise ValueError("bridge key is required")
        self.source_provider = str(source_provider)
        self.target_provider = str(target_provider)
        self.key = str(key)
        self.state = TransactionState.PENDING

    def commit(self) -> None:
        if self.state != TransactionState.PENDING:
            raise RuntimeError("Transaction commit requires PENDING state")
        self.state = TransactionState.COMMITTED

    def read(self, requesting_provider: str) -> None:
        if self.state != TransactionState.COMMITTED:
            raise RuntimeError("Bridge read is forbidden before committed barrier")
        if str(requesting_provider) != self.target_provider:
            raise PermissionError("Bridge read target isolation violation")
        self.state = TransactionState.BARRIER_OPEN

    def reject(self) -> None:
        self.state = TransactionState.REJECTED


class ProviderExecutionContract:
    """Validate the result envelope before a provider result is trusted."""

    @staticmethod
    def validate_success(result: Mapping[str, Any], seat_key: str = "", identity_matcher=None) -> None:
        if not isinstance(result, Mapping):
            raise ValueError("provider result must be a mapping")
        if str(result.get("status") or "").upper() != "SUCCESS":
            raise ValueError("provider result is not SUCCESS")
        if str(result.get("seat") or "").strip() != str(seat_key).strip():
            raise ValueError("provider seat identity mismatch")
        content = str(result.get("content") or "").strip()
        if not content:
            raise ValueError("successful provider result has no content")
        executed = str(result.get("executed_model") or "").strip()
        declared = str(result.get("model") or "").strip()
        provider_reported = str(result.get("provider_reported_model") or "").strip()
        if not executed or declared != executed:
            raise ValueError("executed model identity mismatch")
        # Some official APIs do not echo the model in their response. In that
        # case the requested, explicitly selected model remains the execution
        # identity; when the provider does echo a model it must match exactly.
        if provider_reported:
            matches = identity_matcher(executed, provider_reported) if identity_matcher else provider_reported.lower() == executed.lower()
            if not matches:
                raise ValueError("provider-reported model mismatch")
        attempted = [str(x).strip() for x in (result.get("attempted_models") or []) if str(x).strip()]
        if attempted and attempted[-1] != executed:
            raise ValueError("cascade position does not match executed model")
        position = result.get("cascade_position")
        if position is not None and int(position) != (attempted.index(executed) + 1 if executed in attempted else int(position)):
            raise ValueError("cascade position mismatch")

    @staticmethod
    def validate_failure(result: Mapping[str, Any]) -> None:
        if str(result.get("status") or "").upper() == "SUCCESS":
            raise ValueError("failure contract cannot contain SUCCESS")
        classification = str(result.get("classification") or "UNKNOWN").upper()
        if classification not in FAILURE_CLASSES and classification != "NO_FREE_MODEL_CONFIGURED":
            raise ValueError("invalid failure classification")


class FreeCascadeController:
    """Strict #1→#10 controller; it never invents or reorders model candidates."""

    def __init__(self, candidates: Sequence[str], policy: TimeoutRetryPolicy | None = None):
        clean = []
        for model in candidates:
            value = str(model or "").strip()
            if value and value not in clean:
                clean.append(value)
        self.candidates = tuple(clean[:FREE_CASCADE_MAX])
        self.policy = (policy or TimeoutRetryPolicy()).bounded()
        self.position = 0

    def next_model(self) -> Optional[str]:
        if self.position >= min(len(self.candidates), self.policy.cascade_max_models):
            return None
        model = self.candidates[self.position]
        self.position += 1
        return model

    @staticmethod
    def should_continue(classification: str, has_next_model: bool) -> bool:
        if not has_next_model:
            return False
        cls = str(classification or "UNKNOWN").upper()
        return cls not in {"AUTHENTICATION_ERROR", "EXECUTION_IDENTITY_MISMATCH", "NOT_CONFIGURED", "CONFIGURATION"}

    @staticmethod
    def classify_attempt(status: Optional[int], classification: str) -> str:
        cls = str(classification or "UNKNOWN").upper()
        if cls in FAILURE_CLASSES:
            return cls
        if status == 401 or status == 403:
            return "AUTHENTICATION_ERROR"
        if status == 408:
            return "TIMEOUT"
        if status is not None and status >= 500:
            return "API_ERROR"
        return "UNKNOWN"
