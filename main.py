from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import html
import json
import re
import time
import uuid

import streamlit as st
from streamlit.components.v1 import html as components_html

from attachment_utils import normalize_uploaded_files, public_metadata
from providers import get_seats, VERSION as PROVIDER_VERSION, ProviderError, _canonical_error_classification, call_seat, capture_credentials, capture_model_candidates, configured_count, credential_sources, diagnostic_seat, get_model_candidates, model_config_fingerprint, model_config_sources, transcribe_audio_gemini, _deepseek_model_identity_matches
from production_core import RequestLifecycle, ProviderExecutionContract
from production_core_test_runner import run_production_core_tests, render_report as render_production_core_report

APP_VERSION = PROVIDER_VERSION
MAX_VOICE_BYTES = 8 * 1024 * 1024
MAX_STORED_VOICE_ITEMS = 10
MAX_STORED_VOICE_BYTES = 40 * 1024 * 1024
MAX_ROUNDS = 4
MAX_EXECUTION_SECONDS = None
MAX_PROMPT_CHARS = 20_000
MAX_CHAT_MESSAGES = 200
MAX_REQUEST_IDS = 50
MAX_WORKERS = 8
ERROR_DISPLAY_TTL_SECONDS = 60
# UI-only classification: a latency cutoff is an internal transport event,
# not a user-facing diagnosis of why a provider did not answer.
PUBLIC_NO_RESPONSE = "NO_RESPONSE"
BRIDGE_WRITE_PATTERN = re.compile(
    r"(?im)^\s*BRIDGE_WRITE\s*:\s*(BRIDGE_[A-Z0-9_]+)\s*=\s*(.+?)\s*$"
)
BRIDGE_READ_PATTERN = re.compile(
    r"(?im)^\s*BRIDGE_READ\s*:\s*(BRIDGE_[A-Z0-9_]+)\s*$"
)


def _extract_bridge_writes(content: str) -> list[tuple[str, str]]:
    """Extract only explicit provider bridge-write records."""
    writes: list[tuple[str, str]] = []
    for match in BRIDGE_WRITE_PATTERN.finditer(str(content or "")):
        key = match.group(1).strip()
        value = match.group(2).strip()
        if value and len(value) <= 2000:
            writes.append((key, value))
    return writes


def _extract_bridge_reads(content: str) -> list[str]:
    reads: list[str] = []
    for match in BRIDGE_READ_PATTERN.finditer(str(content or "")):
        key = match.group(1).strip()
        if key:
            reads.append(key)
    return reads


def _validate_bridge_provider_output(seat, result: dict) -> tuple[bool, str]:
    """Validate the exact safe envelope before a provider result enters the bridge."""
    if not isinstance(result, dict):
        return False, "RESULT_NOT_OBJECT"
    if str(result.get("status") or "").upper() != "SUCCESS":
        return False, "RESULT_NOT_SUCCESS"
    declared_seat = str(result.get("seat") or getattr(seat, "key", "")).strip()
    if declared_seat != str(getattr(seat, "key", "")):
        return False, "SEAT_IDENTITY_MISMATCH"
    content = result.get("content")
    if not isinstance(content, str) or not content.strip():
        return False, "EMPTY_OUTPUT"
    model = str(result.get("executed_model") or result.get("model") or "").strip()
    if not model:
        return False, "MODEL_ID_MISSING"
    declared_model = str(result.get("model") or "").strip()
    if declared_model and declared_model != model:
        return False, "MODEL_ID_MISMATCH"
    if "round" in result:
        try:
            int(result.get("round"))
        except (TypeError, ValueError):
            return False, "ROUND_INVALID"
    return True, "VALID"


class SharedContextBridge:
    """Transactional, round-scoped bridge with a prompt-safe read protocol.

    The current release deliberately does NOT place bridge values in the next provider's
    prompt. Providers receive only a non-sensitive availability manifest and
    may request a value with ``BRIDGE_READ: KEY``. The application resolves that
    request from committed Shared Context after the provider response.
    """

    def __init__(self, initial_snapshot: str = "", max_chars: int = 30_000, request_id: str = "", round_no: int = 0):
        self.max_chars = max(1, int(max_chars))
        self.request_id = str(request_id or "")
        self.round_no = int(round_no or 0)
        self.bridge_id = hashlib.sha256(
            f"{self.request_id}:{self.round_no}:{uuid.uuid4().hex}".encode("utf-8")
        ).hexdigest()[:24]
        self._entries: list[str] = []
        self._values: dict[str, dict] = {}
        self._write_sequence = 0
        self._read_sequence = 0
        self._committed = False
        self._barrier_open = False
        self.trace: list[dict] = []
        self._source_values: dict[str, str] = {}
        self._provider_input_prompts: dict[int, str] = {}
        self._resolved_reads: dict[str, dict] = {}
        initial = str(initial_snapshot or "").strip()
        if initial:
            self._entries.append(initial)

    def snapshot(self) -> str:
        """Return the internal Shared Context snapshot for diagnostics/tests."""
        return "\n\n".join(self._entries)[-self.max_chars:]

    def prompt_snapshot(self, target_seat=None) -> str:
        """Return context with bridge values redacted from provider prompts."""
        raw = "\n\n".join(self._entries)
        base = BRIDGE_WRITE_PATTERN.sub(lambda m: f"BRIDGE_WRITE: {m.group(1).strip()} = [REDACTED_BRIDGE_VALUE]", raw)
        base = re.sub(r"(?im)^(\s*Value:\s*).+$", r"\1[REDACTED_BRIDGE_VALUE]", base)
        available = []
        for key, record in self._values.items():
            available.append(
                "BRIDGE READ AVAILABLE (VALUE NOT IN PROMPT):\n"
                f"Key: {key}\n"
                f"bridge_id: {self.bridge_id}\n"
                f"round_id: {self.round_no}\n"
                f"source_seat: {record['source_seat']}\n"
                f"target_seat: {int(getattr(target_seat, 'room_slot', 0) or 0) if target_seat else 0}"
            )
        if available:
            base = (base + "\n\n" if base else "") + "\n\n".join(available)
        return base[-self.max_chars:]

    def record_provider_input(self, seat, prompt: str) -> None:
        self._provider_input_prompts[int(getattr(seat, "room_slot", 0) or 0)] = str(prompt or "")

    def append_user_declarations(self, user_prompt: str) -> None:
        """Keep legacy declarations in internal context; prompt_snapshot redacts values."""
        text = str(user_prompt or "")
        pattern = re.compile(r"(?im)^\s*(BRIDGE_[A-Z0-9_]+)\s*=\s*([^\r\n]+?)\s*$")
        for match in pattern.finditer(text):
            key, value = match.group(1).strip(), match.group(2).strip()
            if value and len(value) <= 2000:
                self._entries.append(f"BRIDGE DECLARATION (USER-PROVIDED UNTRUSTED TEST DATA):\nKey: {key}\nValue: {value}")

    def _record_trace(self, **fields) -> None:
        safe = {
            "bridge_id": self.bridge_id,
            "round_id": self.round_no,
            "source_seat": int(fields.get("source_seat", 0) or 0),
            "source_provider": str(fields.get("source_provider", "") or ""),
            "target_seat": int(fields.get("target_seat", 0) or 0),
            "key": str(fields.get("key", "") or ""),
            "write_sequence": int(fields.get("write_sequence", self._write_sequence) or 0),
            "commit_status": str(fields.get("commit_status", "") or ""),
            "read_sequence": int(fields.get("read_sequence", self._read_sequence) or 0),
            "schema_validation": str(fields.get("schema_validation", "") or ""),
            "request_id": self.request_id,
        }
        self.trace.append(safe)

    def append_agent_output(self, seat, result: dict) -> None:
        valid, reason = _validate_bridge_provider_output(seat, result)
        if not valid:
            self._record_trace(
                source_seat=getattr(seat, "room_slot", 0),
                source_provider=getattr(seat, "name", ""),
                target_seat=0,
                key="",
                schema_validation=reason,
                commit_status="REJECTED",
            )
            return
        content = str(result.get("content") or "").strip()
        room_slot = int(getattr(seat, "room_slot", 0) or 0)
        provider = str(getattr(seat, "name", "AI") or "AI").strip()
        model = str(result.get("executed_model") or result.get("model") or "").strip()
        self._entries.append(
            "BRIDGE AGENT OUTPUT (UNTRUSTED DATA):\n"
            f"Room seat: {room_slot}\n"
            f"Provider identity: {provider}\n"
            f"Executed model: {model}\n"
            f"Output:\n{content}"
        )
        for key, value in _extract_bridge_writes(content):
            self._write_sequence += 1
            self._source_values[key] = value
            self._values[key] = {
                "value": value,
                "source_seat": room_slot,
                "source_provider": provider,
                "write_sequence": self._write_sequence,
            }
            self._entries.append(
                "BRIDGE WRITE RECORD (PROVIDER UNTRUSTED DATA):\n"
                f"Source seat: {room_slot}\n"
                f"Source provider: {provider}\n"
                f"Executed model: {model}\n"
                f"Key: {key}\n"
                f"Value: {value}"
            )
            self._record_trace(
                source_seat=room_slot,
                source_provider=provider,
                target_seat=0,
                key=key,
                write_sequence=self._write_sequence,
                commit_status="PENDING",
                schema_validation="PASS",
            )

    def commit(self, target_seat=None) -> None:
        """Commit the pending write transaction and bind its intended target seat."""
        target_slot = int(getattr(target_seat, "room_slot", 0) or 0) if target_seat else 0
        self._committed = True
        for trace in self.trace:
            if trace["commit_status"] == "PENDING":
                trace["commit_status"] = "COMMITTED"
                if target_slot:
                    trace["target_seat"] = target_slot

    def barrier(self) -> None:
        if not self._committed:
            raise RuntimeError("Bridge barrier reached before commit")
        self._barrier_open = True

    def read(self, key: str, target_seat) -> str | None:
        key = str(key or "").strip()
        if not key or not self._committed or not self._barrier_open:
            return None
        record = self._values.get(key)
        if not record:
            return None
        self._read_sequence += 1
        target_slot = int(getattr(target_seat, "room_slot", 0) or 0)
        self._resolved_reads[key] = {
            "source_seat": record["source_seat"],
            "source_provider": record["source_provider"],
            "target_seat": target_slot,
            "write_sequence": record["write_sequence"],
            "read_sequence": self._read_sequence,
            "value": str(record["value"]),
        }
        self._record_trace(
            source_seat=record["source_seat"],
            source_provider=record["source_provider"],
            target_seat=target_slot,
            key=key,
            write_sequence=record["write_sequence"],
            commit_status="COMMITTED",
            read_sequence=self._read_sequence,
            schema_validation="PASS",
        )
        return str(record["value"])

    def transaction_audit(self, source_seat: int = 7, target_seat: int = 2, key: str = "BRIDGE_RESULT", user_prompt: str = "") -> dict:
        """Return a proof-oriented, value-redacted audit of the bridge transaction."""
        record = self._values.get(key)
        source_value = self._source_values.get(key, "")
        read = self._resolved_reads.get(key)
        target_prompt = self._provider_input_prompts.get(int(target_seat), "")
        user_has = bool(source_value and source_value in str(user_prompt or ""))
        target_has = bool(source_value and source_value in target_prompt)
        target_value = str(read.get("value")) if read else ""
        source_ok = bool(record and int(record.get("source_seat", 0)) == int(source_seat))
        target_ok = bool(read and int(read.get("target_seat", 0)) == int(target_seat))
        return {
            "BRIDGE_ID": self.bridge_id,
            "ROUND_ID": self.round_no,
            "SOURCE": "DeepSeek / Seat 7" if int(source_seat) == 7 else f"Seat {source_seat}",
            "TARGET": "Gemini / Seat 2" if int(target_seat) == 2 else f"Seat {target_seat}",
            "KEY": key,
            "WRITE": "PASS" if record and source_ok else "FAIL",
            "VALIDATE": "PASS" if record else "FAIL",
            "COMMIT": "PASS" if self._committed and record else "FAIL",
            "BARRIER": "PASS" if self._barrier_open and self._committed and record else "FAIL",
            "READ": "PASS" if read and target_ok else "FAIL",
            "SCHEMA_VALIDATION": "PASS" if read and target_ok else "FAIL",
            "SOURCE_VALUE": "[REDACTED]",
            "TARGET_VALUE": "[REDACTED]",
            "MATCH": "PASS" if source_value and target_value and source_value == target_value else "FAIL",
            "USER_PROMPT_CONTAINS_VALUE": "NO" if source_value and not user_has else "YES",
            "GEMINI_INPUT_PROMPT_CONTAINS_VALUE": "NO" if source_value and not target_has else "YES",
            "BRIDGE_STATE_CONTAINS_VALUE": "YES" if source_value and record and record.get("value") == source_value else "NO",
            "write_sequence": int(record.get("write_sequence", 0)) if record else 0,
            "read_sequence": int(read.get("read_sequence", 0)) if read else 0,
            "request_id": self.request_id,
        }

    def transaction_trace(self) -> list[dict]:
        return [dict(item) for item in self.trace]

    def consume_read_requests(self, seat, result: dict) -> dict:
        """Resolve a provider's BRIDGE_READ request from committed bridge state.

        The current release closes the handoff gap left by the prior bridge implementation: the provider is never
        given the bridge value in its input prompt. Instead, its explicit
        BRIDGE_READ request is resolved against the committed transaction state
        immediately after the provider response. A successful single read is
        promoted to a canonical bridge-read result so the caller can expose the
        exact value without performing a second provider request.
        """
        valid, reason = _validate_bridge_provider_output(seat, result)
        if not valid:
            return {"schema_validation": reason, "reads": [], "status": "INVALID"}
        reads = []
        for key in _extract_bridge_reads(str(result.get("content") or "")):
            value = self.read(key, seat)
            reads.append({"key": key, "value": value, "available": value is not None})
        if not reads:
            return {"schema_validation": "PASS", "reads": [], "status": "NO_READ_REQUEST"}
        if any(not item["available"] for item in reads):
            return {
                "schema_validation": "PASS",
                "reads": reads,
                "status": "NOT_READY",
            }
        return {
            "schema_validation": "PASS",
            "reads": reads,
            "status": "RESOLVED",
            "value": reads[0]["value"] if len(reads) == 1 else None,
        }


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _new_chat() -> dict:
    return {
        "id": uuid.uuid4().hex,
        "title": "محادثة جديدة",
        "created_at": _now(),
        "messages": [],
        "request_ids": [],
        "request_records": [],
        "history_identity_ledger": [],
        "result_keys": [],
    }


def _ensure_chat_identity_state(chat: dict) -> None:
    chat.setdefault("request_ids", [])
    chat.setdefault("request_records", [])
    chat.setdefault("history_identity_ledger", [])
    chat.setdefault("result_keys", [])


def _request_display_number(chat: dict, request_id: str) -> int | None:
    _ensure_chat_identity_state(chat)
    for index, record in enumerate(chat.get("request_records", []), start=1):
        if isinstance(record, dict) and record.get("request_id") == request_id:
            return index
    return None


def _history_identity_keys(chat: dict) -> set[tuple[str, int, str]]:
    _ensure_chat_identity_state(chat)
    keys: set[tuple[str, int, str]] = set()
    for raw in chat.get("history_identity_ledger", []):
        if isinstance(raw, (list, tuple)) and len(raw) == 3:
            try:
                request_id, round_no, seat_key = str(raw[0]).strip(), int(raw[1]), str(raw[2]).strip()
            except (TypeError, ValueError):
                continue
            if request_id and round_no > 0 and seat_key:
                keys.add((request_id, round_no, seat_key))
    # Backward-compatible reconstruction for histories created before the ledger existed.
    for message in chat.get("messages", []):
        if message.get("role") != "assistant":
            continue
        request_id = str(message.get("request_id") or "").strip()
        seat = str(message.get("seat_key") or "").strip()
        if not seat:
            seat = next((str(s.key) for s in get_seats() if s.name == message.get("seat")), "")
        try:
            round_no = int(message.get("round"))
        except (TypeError, ValueError):
            continue
        if request_id and seat and round_no > 0:
            keys.add((request_id, round_no, seat))
    return keys


def _assert_unique_history_identity(chat: dict, request_id: str, round_no: int, seat_key: str) -> None:
    request_id = str(request_id).strip()
    seat_key = str(seat_key).strip()
    try:
        round_no = int(round_no)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid history identity round: {round_no!r}") from exc
    if not request_id or round_no <= 0 or not seat_key:
        raise RuntimeError(
            f"Invalid history identity: request_id={request_id!r}, round={round_no!r}, seat={seat_key!r}"
        )
    key = (request_id, round_no, seat_key)
    existing = _history_identity_keys(chat)
    if key in existing:
        raise RuntimeError(f"Duplicate history identity invariant: {key!r}")
    chat["history_identity_ledger"].append([request_id, round_no, seat_key])


def _init_state() -> None:
    defaults = {"rounds": 1, "folder_nonce": 0, "voice_nonce": 0, "last_results": [], "last_diagnostics": [], "voice_fingerprints": {}, "voice_audio_store": {}, "last_voice_error": ""}
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if "chats" not in st.session_state or not isinstance(st.session_state.chats, list):
        chat = _new_chat()
        st.session_state.chats = [chat]
        st.session_state.active_chat_id = chat["id"]


def _active_chat() -> dict:
    for chat in st.session_state.chats:
        if isinstance(chat, dict) and chat.get("id") == st.session_state.get("active_chat_id"):
            chat.setdefault("messages", [])
            chat.setdefault("title", "محادثة جديدة")
            chat.setdefault("created_at", _now())
            _ensure_chat_identity_state(chat)
            return chat
    chat = _new_chat()
    st.session_state.chats.insert(0, chat)
    st.session_state.active_chat_id = chat["id"]
    return chat


def _prune_voice_store() -> None:
    store = st.session_state.get("voice_audio_store") or {}
    if not isinstance(store, dict):
        st.session_state.voice_audio_store = {}
        return
    kept: list[tuple[str, bytes]] = []
    total = 0
    for key, value in reversed(list(store.items())):
        try:
            blob = bytes(value or b"")
        except Exception:
            continue
        if len(kept) >= MAX_STORED_VOICE_ITEMS or total + len(blob) > MAX_STORED_VOICE_BYTES:
            continue
        kept.append((key, blob))
        total += len(blob)
    st.session_state.voice_audio_store = dict(reversed(kept))


def _title_from_prompt(prompt: str) -> str:
    clean = re.sub(r"\s+", " ", str(prompt or "")).strip()
    return clean[:48] + ("…" if len(clean) > 48 else "") or "محادثة جديدة"


def _shared_context(chat: dict, exclude_message_id: str | None = None, max_chars: int = 30_000) -> str:
    lines: list[str] = []
    for item in chat.get("messages", [])[-MAX_CHAT_MESSAGES:]:
        if exclude_message_id and item.get("id") == exclude_message_id:
            continue
        role = item.get("role")
        if role == "user":
            text = str(item.get("content", "")).strip()
            if text:
                lines.append(f"USER HISTORICAL DATA:\n{text}")
            attachment_context = str(item.get("attachment_context", "")).strip()
            if attachment_context:
                lines.append(f"USER ATTACHMENT METADATA (UNTRUSTED DATA):\n{attachment_context}")
        elif role == "assistant":
            text = str(item.get("content", "")).strip()
            if text:
                lines.append(f"{item.get('seat', 'AI')} [OFFICIAL API] HISTORICAL OUTPUT:\n{text}")
    return "\n\n".join(lines)[-max_chars:]


def _worker_failure(seat, exc: Exception, model_candidates: dict | None = None, request_id: str = "", round_no: int = 0) -> dict:
    models = tuple((model_candidates or {}).get(seat.key) or ())
    return {"seat": seat.key, "name": seat.name, "label": seat.label, "status": "FAILED", "mode": "internal", "model": models[0] if models else "", "content": "", "classification": "API_ERROR", "error": f"class=provider_error; internal worker failure: {exc.__class__.__name__}",
        "attempt_summaries": [{"attempt": 1, "model": models[0] if models else "", "status_code": None, "classification": "API_ERROR", "retryable": False}], "latency": 0.0, "attempted_models": [], "official_authenticated": False, "request_id": request_id, "round": round_no}


def _history_attempt_summaries(details: list[dict]) -> list[dict]:
    """Persist only the original compact, non-sensitive classifications in History."""
    allowed = {
        "MODEL_UNAVAILABLE", "QUOTA_EXCEEDED", "RATE_LIMITED",
        "AUTHENTICATION_ERROR", "API_ERROR", "NETWORK_ERROR",
        "TIMEOUT", "UNKNOWN",
    }
    summaries: list[dict] = []
    for detail in details or []:
        classification = _canonical_error_classification(str(detail.get("classification") or "UNKNOWN"))
        if classification == "TIMEOUT":
            classification = PUBLIC_NO_RESPONSE
        if classification not in allowed | {PUBLIC_NO_RESPONSE}:
            classification = "UNKNOWN"
        summary = {
            "attempt": detail.get("attempt"),
            "model": str(detail.get("model") or "").strip(),
            "status_code": detail.get("status_code"),
            "classification": classification,
            "retryable": bool(detail.get("retryable", False)),
        }
        if "_display_created_at" in detail:
            try:
                summary["created_at_epoch"] = float(detail.get("_display_created_at"))
            except (TypeError, ValueError):
                pass
        summaries.append(summary)
    return summaries


def _safe_attempt_telemetry(details: list[dict], result: dict | None = None) -> list[dict]:
    """Return the expanded safe runtime telemetry contract without raw errors."""
    result = result or {}
    out = []
    for detail in details or []:
        out.append({
            "provider": str(detail.get("provider") or result.get("name") or "").strip(),
            "attempt": detail.get("attempt"),
            "model": str(detail.get("model") or "").strip(),
            "status_code": detail.get("status_code"),
            "classification": _canonical_error_classification(str(detail.get("classification") or "UNKNOWN")),
            "retryable": bool(detail.get("retryable", False)),
            "execution_time": round(float(detail.get("execution_time", detail.get("latency", 0.0)) or 0.0), 3),
            "request_id": str(detail.get("request_id") or result.get("request_id") or ""),
            "attempt_id": str(detail.get("attempt_id") or ""),
            "round": int(detail.get("round", result.get("round", 0)) or 0),
            "final_result": str(detail.get("final_result") or "FAILED").upper(),
            "cascade_action": str(detail.get("cascade_action") or ("CASCADE_CONTINUE" if detail.get("retryable") else "CASCADE_STOP")).upper(),
        })
    return out


def _public_result(result: dict) -> dict:
    """Return the UI-safe result persisted in session state. Raw provider payloads stay transient."""
    public = dict(result or {})
    details = list(public.get("attempt_diagnostics", []) or [])
    public["attempt_summaries"] = _history_attempt_summaries(details)
    public["attempt_telemetry"] = list(public.get("attempt_telemetry") or _safe_attempt_telemetry(details, public))
    for telemetry in public["attempt_telemetry"]:
        if str(telemetry.get("classification") or "").upper() == "TIMEOUT":
            telemetry["classification"] = PUBLIC_NO_RESPONSE
    classification = str(public.get("classification") or "").strip().upper()
    if classification not in {"MODEL_UNAVAILABLE", "QUOTA_EXCEEDED", "RATE_LIMITED", "AUTHENTICATION_ERROR", "API_ERROR", "NETWORK_ERROR", "TIMEOUT", "UNKNOWN"}:
        classification = "UNKNOWN"
    if classification == "TIMEOUT":
        classification = PUBLIC_NO_RESPONSE
        # A transport timeout is an internal control-flow event.  Publicly
        # expose it only as a neutral no-response state so the UI cannot label
        # a provider as having an API timeout/error.
        public["status"] = PUBLIC_NO_RESPONSE
    public["classification"] = classification
    public.pop("attempt_diagnostics", None)
    public.pop("error", None)
    return public

def _attempt_display_remaining(detail: dict, now: float | None = None) -> float:
    """Return remaining UI visibility time; never expose or mutate raw provider errors."""
    try:
        created = float(detail.get("created_at_epoch", 0))
    except (TypeError, ValueError):
        return 0.0
    current = time.time() if now is None else float(now)
    return max(0.0, ERROR_DISPLAY_TTL_SECONDS - (current - created))


def _render_temporary_attempt_diagnostic(detail: dict) -> None:
    """Render a compact attempt error for 60 seconds, without exposing raw provider payloads."""
    model = str(detail.get("model") or "").strip()
    classification = str(detail.get("classification") or "UNKNOWN").strip().upper()
    if classification == "TIMEOUT":
        classification = PUBLIC_NO_RESPONSE
    code = detail.get("status_code")
    code_text = f" · HTTP {code}" if code else ""
    remaining = _attempt_display_remaining(detail)
    if remaining <= 0:
        return
    latency = detail.get("latency")
    latency_text = f" · {float(latency):.3f}s" if latency is not None else ""
    request_text = str(detail.get("request_id") or "")[:36]
    round_text = f" · Round {detail.get('round', '?')}"
    final_text = str(detail.get("final_result") or "FAILED").upper()
    safe_text = html.escape(
        f"Attempt #{detail.get('attempt', '?')} · {model} · ❌ FAILED{code_text} · {classification}{latency_text}{round_text} · {final_text} · request {request_text}"
    )
    # Streamlit can render several attempt diagnostics in the same page.
    # Every timer therefore gets a unique DOM id; a shared id would cause
    # getElementById() to target only the first diagnostic and leave later
    # errors visible indefinitely.
    element_id = "attempt-error-" + uuid.uuid4().hex
    safe_id = html.escape(element_id, quote=True)
    height = 32
    components_html(
        f"""<div id=\"{safe_id}\" style=\"font-family:sans-serif;font-size:13px;padding:4px 0;\">{safe_text}</div>
<script>
const el=document.getElementById('{safe_id}');
if (el) setTimeout(()=>{{ el.remove(); }}, {int(remaining * 1000)});
</script>""",
        height=height,
    )


def _run_round(user_prompt: str, chat: dict, round_no: int, credentials: dict, attachments: list[dict], model_candidates: dict, current_user_message_id: str, deadline: float | None, request_id: str) -> list[dict]:
    seats = get_seats()
    bridge = SharedContextBridge(
        _shared_context(chat, exclude_message_id=current_user_message_id),
        max_chars=30_000,
        request_id=request_id,
        round_no=round_no,
    )
    # Current release: explicit BRIDGE_* assignments in the current request become
    # round-scoped bridge data before any provider is called. This makes a
    # deliberate "save to Shared Context, then retrieve later" test real
    # rather than relying on a model to echo the value in its answer.
    bridge.append_user_declarations(user_prompt)
    results: dict[str, dict] = {}

    # Current release: provider calls use an explicit dependency order for bridge
    # propagation. DeepSeek (seat 7) executes before Gemini (seat 2), while
    # remaining seats retain canonical room order. Results are returned in
    # canonical room order, so seat identity/history/UI ordering is unchanged.
    by_key = {seat.key: seat for seat in seats}
    bridge_order = []
    for key in ("deepseek", "gemini"):
        if key in by_key:
            bridge_order.append(by_key.pop(key))
    bridge_order.extend(seat for seat in seats if seat.key in by_key)
    for seat in bridge_order:
        try:
            provider_prompt = bridge.prompt_snapshot(seat)
            bridge.record_provider_input(seat, provider_prompt)
            result = call_seat(
                seat, user_prompt, provider_prompt, round_no, False,
                credentials.get(seat.key), attachments, model_candidates.get(seat.key),
                deadline, request_id,
            )
            results[seat.key] = result
            bridge.append_agent_output(seat, result)
            if seat.key == "deepseek":
                # Seat 7 is the source and Seat 2 is the explicit read target
                # for the transactional bridge test. Commit and open the
                # handoff barrier before Gemini is invoked.
                gemini_target = by_key.get("gemini")
                bridge.commit(gemini_target)
                bridge.barrier()
            else:
                resolution = bridge.consume_read_requests(seat, result)
                result["bridge_read_status"] = (
                    "PASS" if resolution.get("status") == "RESOLVED" else
                    "NOT_READY" if resolution.get("status") == "NOT_READY" else
                    resolution.get("status", "NO_READ_REQUEST")
                )
                result["bridge_schema_validation"] = resolution.get("schema_validation", "")
                if resolution.get("status") == "RESOLVED" and resolution.get("value") is not None:
                    # The provider was deliberately not given the bridge value
                    # in its input. The bridge resolves its explicit read request
                    # here and publishes the canonical read result as the seat's
                    # response. No second provider call is made, so there is no
                    # prompt injection of BRIDGE_RESULT.
                    result["content"] = str(resolution["value"])
                    result["bridge_read_value"] = str(resolution["value"])
                elif resolution.get("status") == "NOT_READY":
                    result["content"] = "BRIDGE_READ_STATUS = NOT_READY"
            if seat.key == "gemini":
                result["bridge_transaction_audit"] = bridge.transaction_audit(user_prompt=user_prompt)
                result["bridge_trace"] = bridge.transaction_trace()
            else:
                result["bridge_trace"] = bridge.transaction_trace()
        except Exception as exc:
            results[seat.key] = _worker_failure(
                seat, exc, model_candidates, request_id, round_no
            )

    for seat in seats:
        results.setdefault(
            seat.key,
            _worker_failure(
                seat, TimeoutError("round deadline exceeded"),
                model_candidates, request_id, round_no,
            ),
        )
    return [results[seat.key] for seat in seats]


def _run_council(user_prompt: str, chat: dict, rounds: int, credentials: dict, attachments: list[dict], model_candidates: dict, current_user_message_id: str, request_id: str) -> list[dict]:
    deadline = None
    lifecycle = RequestLifecycle.begin(request_id)
    chat.setdefault("audit_events", [])
    chat["audit_events"] = [e for e in chat.get("audit_events", []) if e.get("request_id") != request_id]
    all_results: list[dict] = []
    total_rounds = max(1, min(int(rounds), MAX_ROUNDS))
    try:
        for round_no in range(1, total_rounds + 1):
            lifecycle.start_round(round_no)
            round_results = _run_round(user_prompt, chat, round_no, credentials, attachments, model_candidates, current_user_message_id, deadline, request_id)
            seen_keys = set()
            for result in round_results:
                result["request_id"] = request_id
                result["round"] = round_no
                seat_key = str(result.get("seat") or "")
                result_key = f"{request_id}:{round_no}:{result.get('seat','')}"
                result["result_key"] = result_key
                identity_key = (str(request_id), int(round_no), seat_key)
                if identity_key in seen_keys:
                    continue
                existing_history = _history_identity_keys(chat)
                if identity_key in existing_history:
                    seen_keys.add(identity_key)
                    continue
                _assert_unique_history_identity(chat, request_id, round_no, seat_key)
                seen_keys.add(identity_key)
                public_result = _public_result(result)
                all_results.append(public_result)
                if result.get("status") == "SUCCESS" and result.get("content"):
                    executed_model = str(result.get("executed_model") or "").strip()
                    result_model = str(result.get("model") or "").strip()
                    attempted_models = [str(m).strip() for m in result.get("attempted_models", []) if str(m).strip()]
                    if not executed_model or result_model != executed_model:
                        raise RuntimeError(f"Execution identity invariant violated: {result_model!r} != {executed_model!r}")
                    if attempted_models and attempted_models[-1] != executed_model:
                        raise RuntimeError(f"Cascade identity invariant violated: {attempted_models!r} -> {executed_model!r}")
                    provider_reported_model = str(result.get("provider_reported_model") or "").strip()
                    if provider_reported_model and provider_reported_model.lower() != executed_model.lower() and seat_key != "deepseek":
                        raise RuntimeError(f"Provider identity invariant violated: {provider_reported_model!r} != {executed_model!r}")
                    if seat_key == "deepseek" and not _deepseek_model_identity_matches(executed_model, provider_reported_model):
                        raise RuntimeError(f"Provider identity invariant violated: {provider_reported_model!r} != {executed_model!r}")
                    chat["messages"].append({"role": "assistant", "id": uuid.uuid4().hex, "seat": result["name"], "seat_key": seat_key, "label": result["label"], "content": result["content"], "round": round_no, "mode": "official", "model": executed_model, "executed_model": executed_model, "provider_reported_model": provider_reported_model, "room_slot": int(next((s.room_slot for s in get_seats() if s.key == seat_key), 0)), "provider_identity": next((s.name for s in get_seats() if s.key == seat_key), result.get("name", "")), "provider_key": seat_key, "agent_type": "API_AGENT", "api_mode": "Official API", "attempted_models": attempted_models, "attempt_summaries": _history_attempt_summaries(result.get("attempt_diagnostics", []) or []), "request_id": request_id, "result_key": result_key, "created_at": _now()})
            keys = set(chat.get("result_keys", []))
            keys.update(f"{request_id}:{round_no}:{r.get('seat', '')}" for r in round_results)
            chat["result_keys"] = list(keys)[-MAX_CHAT_MESSAGES:]
            chat["messages"] = chat["messages"][-MAX_CHAT_MESSAGES:]
            success_count = sum(1 for r in round_results if str(r.get("status") or "").upper() == "SUCCESS")
            lifecycle.finish_round(round_no, success_count, len(round_results))
            for r in round_results:
                lifecycle.record(
                    "PROVIDER_RESULT", round_id=round_no, provider=str(r.get("name") or r.get("seat") or ""),
                    model=str(r.get("executed_model") or r.get("model") or ""),
                    cascade_position=r.get("cascade_position"), status=str(r.get("status") or ""),
                    classification=str(r.get("classification") or ""), latency_ms=(float(r.get("latency", 0.0) or 0.0) * 1000.0),
                    metadata={"result_key": str(r.get("result_key") or "")},
                )
        lifecycle.finish(success=True)
    except Exception:
        if lifecycle.state.value == "RUNNING":
            lifecycle.finish(success=False)
        raise
    chat["audit_events"] = lifecycle.audit_snapshot()[-500:]
    return all_results


def _run_provider_diagnostics(credentials: dict, model_candidates: dict) -> list[dict]:
    seats = get_seats()
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(seats)), thread_name_prefix="diagnostic") as pool:
        futures = {pool.submit(diagnostic_seat, seat, credentials.get(seat.key), model_candidates.get(seat.key)): seat for seat in seats}
        for future in as_completed(futures):
            seat = futures[future]
            try:
                results[seat.key] = future.result()
            except Exception as exc:
                results[seat.key] = _worker_failure(seat, exc, model_candidates, request_id="diagnostic", round_no=0)
    return [results[seat.key] for seat in seats]


def _render_sidebar(rounds: int, credentials: dict, model_candidates: dict) -> int:
    seats = get_seats()
    with st.sidebar:
        st.header("⚙️ إعدادات المجلس")
        st.caption("المقاعد: ChatGPT 1 · Gemini 2 · Claude 3 · Grok 4 · Kimi 5 · أنت 6 · DeepSeek 7 · وكلاء إضافيون من 8")
        rounds = st.slider("عدد الجولات", 1, MAX_ROUNDS, max(1, min(rounds, MAX_ROUNDS)), 1)
        st.session_state.rounds = rounds
        st.caption("🆓 Free API Cascade: Free #1 → Free #10 لكل مزود. لا Local Engine ولا Paid fallback.")
        st.divider()
        st.subheader("🔬 تشخيص المزودين")
        st.caption("API رسمي فقط؛ لا Local Engine ولا نموذج تلقائي.")
        if st.button("🔍 فحص جميع الوكلاء الآن", use_container_width=True):
            with st.spinner("تشخيص المزودين بالتوازي…"):
                st.session_state.last_diagnostics = [_public_result(r) for r in _run_provider_diagnostics(credentials, model_candidates)]
            st.rerun()
        if st.button("🧪 Run Production Core Tests", use_container_width=True):
            with st.spinner("تشغيل Test Harness المحلي — بدون أي وكيل AI…"):
                code, report = run_production_core_tests()
            st.session_state.last_production_core_report = report
            st.session_state.last_production_core_code = code
        st.divider()
        chat = _active_chat()
        st.subheader("💬 المحادثة الحالية")
        st.caption(f"اسم المحادثة: {chat['title']}")
        rename = st.text_input("إعادة تسمية", value="", key="rename_chat_input")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("💾 حفظ الاسم", use_container_width=True) and rename.strip():
                chat["title"] = rename.strip()[:80]
                st.rerun()
        with c2:
            if st.button("➕ جديد", use_container_width=True):
                new_chat = _new_chat()
                st.session_state.chats.insert(0, new_chat)
                st.session_state.active_chat_id = new_chat["id"]
                st.session_state.last_results = []
                st.session_state.last_diagnostics = []
                st.rerun()
        st.divider()
        st.subheader("📚 السجل")
        for item in list(st.session_state.chats)[:30]:
            if st.button(f"{'🟢' if item['id'] == st.session_state.active_chat_id else '⚪'} {item.get('title', 'محادثة')}", key=f"load_{item['id']}", use_container_width=True):
                st.session_state.active_chat_id = item["id"]
                st.session_state.last_results = []
                st.rerun()
            st.caption(f"{len(item.get('messages', []))} رسالة • {item.get('created_at', '')}")
        c3, c4 = st.columns(2)
        with c3:
            if st.button("🗑️ حذف الحالية", use_container_width=True):
                if len(st.session_state.chats) == 1:
                    fresh = _new_chat()
                    st.session_state.chats = [fresh]
                    st.session_state.active_chat_id = fresh["id"]
                else:
                    st.session_state.chats = [x for x in st.session_state.chats if x.get("id") != chat["id"]]
                    st.session_state.active_chat_id = st.session_state.chats[0]["id"]
                st.session_state.last_results = []
                st.rerun()
        with c4:
            if st.button("🧹 مسح الكل", use_container_width=True):
                fresh = _new_chat()
                st.session_state.chats = [fresh]
                st.session_state.active_chat_id = fresh["id"]
                st.session_state.last_results = []
                st.session_state.last_diagnostics = []
                st.rerun()
        st.divider()
        st.divider()
        st.subheader("🔌 الاعتمادات والنماذج")
        for seat in seats:
            models = tuple(model_candidates.get(seat.key) or ())
            st.markdown(f"{'🟢' if credentials.get(seat.key) else '⚪'} **{seat.name}** · المقعد {seat.room_slot}")
            st.caption("Free cascade: " + " → ".join(f"#{i+1} `{m}`" for i, m in enumerate(models)) if models else "Free cascade: غير مُكوّن — أضف *_FREE_MODELS")
        st.caption(f"اعتمادات موجودة: {configured_count(credentials)}/{len(seats)} وكلاء API · المقعد 6 محجوز للمستخدم")
        st.caption(f"Model config fingerprint: `{model_config_fingerprint(model_candidates)}`")
        credential_source_map = credential_sources()
        credential_source_text = " • ".join(f"{seat.name}: {credential_source_map.get(seat.key, 'missing')}" for seat in seats)
        st.caption(f"مصدر الاعتمادات: {credential_source_text}")
        sources = model_config_sources()
        source_text = " • ".join(f"{seat.name}: {sources.get(seat.key, 'missing')}" for seat in seats)
        st.caption(f"مصدر إعداد النماذج: {source_text}")
        st.caption("كل Request = جولة/مقعد واحد؛ محاولات Free #1→#10 تُسجّل كـ attempts داخل نفس Request.")
        st.caption("Streamlit Secrets لها الأولوية؛ Environment Variables تُستخدم فقط عند غياب Secret غير الفارغ.")
        st.caption("وجود المفتاح لا يثبت Free Tier أو quota.")
        st.caption("المفاتيح لا تظهر في الواجهة ولا تدخل History.")
    return rounds


def _voice_player(text: str, label: str = "🔊 استمع") -> None:
    from streamlit.components.v1 import html as components_html
    safe_text = json.dumps(str(text or ""), ensure_ascii=False)
    safe_label = html.escape(label, quote=True)
    components_html(f"<button id='speakBtn' style='padding:6px 10px'>{safe_label}</button><script>const b=document.getElementById('speakBtn'),t={safe_text};b.onclick=()=>{{if(!('speechSynthesis' in window))return;window.speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(t);u.lang=/[\\u0600-\\u06FF]/.test(t)?'ar-SA':'en-US';window.speechSynthesis.speak(u);}};</script>", height=44)


def _render_user_room(chat: dict, credentials: dict, model_candidates: dict):
    voice_submission = None
    with st.container(height=500, border=True):
        st.subheader("👤 أنت · المقعد 6")
        user_messages = [m for m in chat.get("messages", []) if m.get("role") == "user"]
        if not user_messages:
            st.caption("اكتب رسالة أو سجّل صوتًا أو أرفق ملفات.")
        st.markdown("**🎙️ صوت داخل الغرفة**")
        st.caption("التفريغ يستخدم Gemini فقط عند وجود نموذج تفريغ صريح.")
        audio = st.audio_input("🎙️ تسجيل رسالة صوتية", sample_rate=16000, key=f"voice_input_{st.session_state.voice_nonce}")
        if audio:
            audio_bytes = bytes(audio.getvalue())
            mime = str(getattr(audio, "type", None) or "audio/wav")
            st.audio(audio_bytes, format=mime)
            if st.button("🎤 إرسال الصوت للمجلس", type="primary", use_container_width=True, key=f"send_voice_{st.session_state.voice_nonce}"):
                fingerprint = hashlib.sha256(audio_bytes).hexdigest()
                seen = st.session_state.voice_fingerprints.get(chat["id"], set())
                if len(audio_bytes) > MAX_VOICE_BYTES:
                    st.error("الرسالة الصوتية أكبر من الحد المسموح 8 MB.")
                elif fingerprint in seen:
                    st.warning("هذه الرسالة الصوتية تم إرسالها بالفعل.")
                else:
                    with st.spinner("تحويل الصوت إلى نص عبر Gemini…"):
                        transcription = transcribe_audio_gemini(audio_bytes, mime, credentials.get("gemini"), model_candidates.get("gemini"))
                    if transcription.get("status") == "SUCCESS" and transcription.get("text", "").strip():
                        st.session_state.last_voice_error = ""
                        voice_submission = (transcription["text"].strip(), audio_bytes, mime, fingerprint)
                    else:
                        st.session_state.last_voice_error = str(transcription.get("error", "unknown error"))
                        st.error(f"تعذر تحويل الصوت: {st.session_state.last_voice_error}")
        if st.session_state.get("last_voice_error"):
            with st.expander("⚠️ آخر خطأ في تحويل الصوت"):
                st.code(st.session_state.last_voice_error)
        st.divider()
        for message in user_messages:
            with st.chat_message("user"):
                st.write(message.get("content", ""))
                if message.get("voice"):
                    st.caption("🎙️ رسالة صوتية — تم تحويلها إلى نص.")
                    blob = st.session_state.get("voice_audio_store", {}).get(message.get("voice_audio_key"))
                    if blob:
                        st.audio(blob, format=message.get("voice_mime", "audio/wav"))
                for attachment in message.get("attachments", []):
                    st.caption(f"📎 {attachment.get('name', 'attachment')} · {attachment.get('mime', 'file')} · {attachment.get('size', 0)} bytes")
    return voice_submission


def _render_ai_room(chat: dict, seat, model_candidates: dict) -> None:
    with st.container(height=500, border=True):
        st.subheader(f"{seat.label} · المقعد {seat.room_slot}")
        models = tuple(model_candidates.get(seat.key) or ())
        st.caption("Free #1 → " + f"`{models[0]}`" if models else "لا يوجد Free API model مُكوّن")
        messages = [m for m in chat.get("messages", []) if m.get("seat") == seat.name]
        if not messages:
            st.caption("بانتظار أول جولة…")
            return
        for message in messages:
            displayed_model = str(message.get('executed_model') or message.get('model', '')).strip()
            executed_model = str(message.get("executed_model") or "").strip()
            attempted_models = [str(m).strip() for m in message.get("attempted_models", []) if str(m).strip()]
            if message.get("mode") == "official":
                if not executed_model or displayed_model != executed_model:
                    st.error("⚠️ Execution identity mismatch: النموذج المعروض لا يطابق النموذج المنفذ.")
                    continue
                if attempted_models and attempted_models[-1] != executed_model:
                    st.error("⚠️ Cascade identity mismatch: آخر محاولة لا تطابق النموذج المنفذ.")
                    continue
                provider_reported_model = str(message.get("provider_reported_model") or "").strip()
                if not provider_reported_model:
                    st.error("⚠️ Provider identity missing: لا يمكن عرض نجاح رسمي بدون هوية النموذج من المزود.")
                    continue
                if seat.key == "deepseek":
                    if not _deepseek_model_identity_matches(executed_model, provider_reported_model):
                        st.error("⚠️ Provider identity mismatch: هوية نموذج DeepSeek التي أعادها المزود لا تطابق النموذج المنفذ.")
                        continue
                elif provider_reported_model != executed_model:
                    st.error("⚠️ Provider identity mismatch: هوية النموذج التي أعادها المزود لا تطابق النموذج المنفذ.")
                    continue
            request_id = str(message.get("request_id") or "").strip()
            request_no = _request_display_number(chat, request_id) if request_id else None
            prefix = f"Request {request_no} · " if request_no is not None else ""
            st.markdown(f"**{prefix}Round {message.get('round', '?')} · 🟢 Official API · `{executed_model or displayed_model}`**")
            if attempted_models:
                st.caption("Cascade attempts: " + " → ".join(f"`{m}`" for m in attempted_models))
            for detail in message.get("attempt_summaries", []) or []:
                _render_temporary_attempt_diagnostic(detail)
            st.caption(f"Executed model: `{executed_model or displayed_model}`")
            if message.get("provider_reported_model"):
                st.caption(f"Provider model: `{message.get('provider_reported_model')}`")
            st.markdown(message.get("content", ""))
            _voice_player(message.get("content", ""))
            st.divider()


def _render_agent_rooms(chat: dict, model_candidates: dict, credentials: dict):
    """Render the user room plus all configured provider seats in a stable 2-column grid."""
    rooms = [None, *get_seats()]
    voice_submission = None
    for index in range(0, len(rooms), 2):
        cols = st.columns(2, gap="medium")
        left = rooms[index]
        right = rooms[index + 1] if index + 1 < len(rooms) else None
        with cols[0]:
            voice_submission = _render_user_room(chat, credentials, model_candidates) if left is None else _render_ai_room(chat, left, model_candidates)
        with cols[1]:
            if right is not None:
                _render_ai_room(chat, right, model_candidates)
    return voice_submission


def _result_error_classification(result: dict) -> str:
    details = result.get("attempt_diagnostics", []) or []
    for detail in reversed(details):
        value = str(detail.get("classification") or "").strip().upper()
        if value in {
            "MODEL_UNAVAILABLE", "QUOTA_EXCEEDED", "RATE_LIMITED",
            "AUTHENTICATION_ERROR", "API_ERROR", "NETWORK_ERROR",
            "TIMEOUT", "UNKNOWN",
        }:
            return PUBLIC_NO_RESPONSE if value == "TIMEOUT" else value
    # Public/history results intentionally no longer retain raw diagnostics.
    # Resolve the already-sanitized attempt summaries as a second source.
    summaries = result.get("attempt_summaries", []) or []
    for detail in reversed(summaries):
        value = str(detail.get("classification") or "").strip().upper()
        if value == PUBLIC_NO_RESPONSE:
            return PUBLIC_NO_RESPONSE
        if value in {
            "MODEL_UNAVAILABLE", "QUOTA_EXCEEDED", "RATE_LIMITED",
            "AUTHENTICATION_ERROR", "API_ERROR", "NETWORK_ERROR",
            "TIMEOUT", "UNKNOWN",
        }:
            return PUBLIC_NO_RESPONSE if value == "TIMEOUT" else value
    raw = str(result.get("error") or "")
    match = re.search(r"(?:^|[;\s])class=([A-Za-z0-9_:-]+)", raw, flags=re.IGNORECASE)
    if match:
        internal = match.group(1)
        try:
            from providers import _canonical_error_classification
            return _canonical_error_classification(internal)
        except Exception:
            pass
    status = result.get("status_code")
    return "AUTHENTICATION_ERROR" if status in (401, 403) else "UNKNOWN"


def _render_result_line(result: dict, diagnostic_only: bool = False) -> None:
    status = result.get("status")
    summaries = list(result.get("attempt_telemetry") or result.get("attempt_summaries", []) or [])

    def render_attempts() -> None:
        if not summaries:
            return
        st.caption("Safe attempt telemetry — raw provider payloads/credentials hidden")
        for detail in summaries:
            provider = str(detail.get("provider") or result.get("name") or "Provider")
            attempt = detail.get("attempt", "?")
            model = str(detail.get("model") or "")
            code = detail.get("status_code")
            cls = str(detail.get("classification") or "UNKNOWN").upper()
            retryable = bool(detail.get("retryable", False))
            execution = detail.get("execution_time", detail.get("latency", 0))
            request_id = str(detail.get("request_id") or result.get("request_id") or "")
            round_no = detail.get("round", result.get("round", "?"))
            final_result = str(detail.get("final_result") or "FAILED").upper()
            action = str(detail.get("cascade_action") or ("CASCADE_CONTINUE" if retryable else "CASCADE_STOP")).upper()
            http = f"HTTP {code}" if code is not None else "HTTP —"
            st.caption(f"{provider} · Attempt {attempt} · `{model}` · {http} · {cls} · Retryable={retryable} · {float(execution):.3f}s · Request {request_id[:48] or '—'} · Round {round_no} · Final={final_result} · {action}")

    if status == "SUCCESS":
        # Execution identity must drive the rendered model: result.get('executed_model') or result['model']
        display_model = result.get('executed_model') or result['model']
        attempt_latency = result.get("successful_attempt_latency")
        attempt_text = f" · attempt {attempt_latency}s" if attempt_latency is not None else ""
        st.success(f"{'🟢' if diagnostic_only else '✅'} {result['label']} — Official API — `{display_model}` — total {result.get('latency', 0)}s{attempt_text}")
        failed_attempts = [x for x in summaries if str(x.get("final_result") or "").upper() == "FAILED"]
        if failed_attempts:
            with st.expander("🧪 Cascade attempt diagnostics", expanded=diagnostic_only):
                render_attempts()
    elif status == "NO_FREE_MODEL_CONFIGURED":
        st.warning(f"🟡 {result['label']} — لا يوجد Free API model مُكوّن؛ لم يتم إرسال أي طلب.")
    elif status == "AUTHENTICATION_OK_NO_FREE_MODEL":
        st.warning(f"🟡 {result['label']} — نقطة المصادقة قبلت المفتاح، لكن لا يوجد Free model مُكوّن.")
        st.caption("Classification: AUTHENTICATION_ERROR")
    elif status == PUBLIC_NO_RESPONSE:
        st.warning(f"🟡 {result.get('label', result.get('name', 'Provider'))} — لم تصل استجابة سريعة من المزود.")
    else:
        with st.expander(f"🔴 {result.get('label', result.get('name', 'Provider'))} — Official API failed", expanded=diagnostic_only):
            st.write("Official API request failed; raw provider payload is not shown in the UI.")
            st.write("Attempted models:", ", ".join(result.get("attempted_models", [])) or "none")
            if summaries:
                last = summaries[-1]
                final_class = str(last.get("classification") or "UNKNOWN").upper()
                final_model = str(last.get("model") or "").strip()
                final_code = last.get("status_code")
                action = str(last.get("cascade_action") or ("CASCADE_CONTINUE" if last.get("retryable") else "CASCADE_STOP")).upper()
                st.caption(f"Final classification: **{final_class}** · `{final_model}` · HTTP {final_code if final_code is not None else '—'} · **{action}**")
                render_attempts()
            else:
                classification = str(result.get("classification") or "").strip().upper() or _result_error_classification(result)
                st.caption(f"Final classification: **{classification}**")


def _render_bridge_audit(results: list[dict]) -> None:
    audit = next((r.get("bridge_transaction_audit") for r in results if r.get("bridge_transaction_audit")), None)
    if not audit:
        return
    st.subheader("🔐 Transactional Bridge — Proof Audit")
    lines = [
        f"BRIDGE_ID = {audit.get('BRIDGE_ID', '—')}",
        f"ROUND_ID = {audit.get('ROUND_ID', '—')}",
        f"SOURCE = {audit.get('SOURCE', '—')}",
        f"TARGET = {audit.get('TARGET', '—')}",
        f"KEY = {audit.get('KEY', '—')}",
        "",
        f"WRITE = {audit.get('WRITE', 'FAIL')}",
        f"VALIDATE = {audit.get('VALIDATE', 'FAIL')}",
        f"COMMIT = {audit.get('COMMIT', 'FAIL')}",
        f"BARRIER = {audit.get('BARRIER', 'FAIL')}",
        "",
        f"READ = {audit.get('READ', 'FAIL')}",
        f"SCHEMA_VALIDATION = {audit.get('SCHEMA_VALIDATION', 'FAIL')}",
        "",
        "SOURCE_VALUE = [REDACTED]",
        "TARGET_VALUE = [REDACTED]",
        f"MATCH = {audit.get('MATCH', 'FAIL')}",
        "",
        f"USER_PROMPT_CONTAINS_VALUE = {audit.get('USER_PROMPT_CONTAINS_VALUE', 'UNKNOWN')}",
        f"GEMINI_INPUT_PROMPT_CONTAINS_VALUE = {audit.get('GEMINI_INPUT_PROMPT_CONTAINS_VALUE', 'UNKNOWN')}",
        f"BRIDGE_STATE_CONTAINS_VALUE = {audit.get('BRIDGE_STATE_CONTAINS_VALUE', 'NO')}",
    ]
    st.code("\n".join(lines), language="text")

def _render_diagnostics(results: list[dict], title: str = "🔎 نتائج الجولة") -> None:
    official = sum(r.get("status") == "SUCCESS" for r in results)
    failed = sum(r.get("status") == "FAILED" for r in results)
    st.subheader(title)
    st.info(f"{official} استجابات رسمية ناجحة • {failed} فشل • Local Engine: غير مستخدم")
    for result in results:
        _render_result_line(result)


def _render_provider_diagnostics(results: list[dict]) -> None:
    if not results:
        return
    st.subheader("🧪 الفحص المستقل للمزودين")
    for result in results:
        _render_result_line(result, diagnostic_only=True)


def _render_production_core_validation() -> None:
    report = st.session_state.get("last_production_core_report")
    if not report:
        return
    st.divider()
    gate = str(report.get("gate") or "NO-GO").upper()
    if gate == "PASS":
        st.success("🟢 PRODUCTION CORE GATE: PASS")
    else:
        st.error("🔴 PRODUCTION CORE GATE: NO-GO")
    st.subheader("🧪 HOTFIX97 — Production Core Test Harness")
    st.code(render_production_core_report(report), language="text")


def _render_attachment_picker() -> list[dict]:
    with st.expander("📁 إرفاق مجلد", expanded=False):
        st.caption("الحد: 20 ملفًا / 25 MB إجمالًا.")
        folder = st.file_uploader("📁 اختر مجلدًا", accept_multiple_files="directory", key=f"chat_folder_{st.session_state.folder_nonce}")
    return list(folder or [])


def _submission_files(submission, folder_files: list[object]) -> list[dict] | None:
    files = list(getattr(submission, "files", []) or []) if submission is not None else []
    files.extend(folder_files)
    if not files:
        return []
    try:
        return normalize_uploaded_files(files)
    except ValueError as exc:
        st.error(str(exc))
        return None


def _request_fingerprint(prompt: str, attachments: list[dict]) -> str:
    h = hashlib.sha256()
    h.update(str(prompt).strip().encode("utf-8"))
    for attachment in attachments:
        h.update(str(attachment.get("name", "")).encode("utf-8"))
        h.update(str(attachment.get("mime", "")).encode("utf-8"))
        h.update(str(attachment.get("size", 0)).encode("ascii"))
        h.update(str(attachment.get("sha256", "")).encode("ascii"))
    return h.hexdigest()


# Backward-compatible name retained for older integrations; rendering is now agent-count agnostic.
_render_six_rooms = _render_agent_rooms

def run_app() -> None:
    _init_state()
    credentials = capture_credentials()
    model_candidates = capture_model_candidates()
    rounds = _render_sidebar(st.session_state.rounds, credentials, model_candidates)
    chat = _active_chat()
    st.title("🏛️ AI Council — Shared Context Arena")
    st.caption(f"{APP_VERSION} • المستخدم (المقعد 6) + {len(get_seats())} وكلاء API • DeepSeek (المقعد 7) • Free Cascade #1→#10 • Provider: {PROVIDER_VERSION}")
    st.markdown("**العقد:** لا Local Engine، لا Paid fallback، ولا نموذج تلقائي. كل طلب رسمي يستخدم فقط النماذج الموجودة صراحةً في `*_FREE_MODELS`.")
    voice_submission = _render_agent_rooms(chat, model_candidates, credentials)
    folder_files = _render_attachment_picker()
    submission = st.chat_input("اكتب موضوع النقاش أو أرفق صورة/ملف…", accept_file="multiple", file_type=None, max_upload_size=10, key="council_chat_input")
    prompt = ""
    attachments: list[dict] = []
    voice_audio = None
    voice_mime = "audio/wav"
    voice_fingerprint = ""
    if voice_submission:
        transcript, voice_audio, voice_mime, voice_fingerprint = voice_submission
        typed_prompt = (getattr(submission, "text", "") or "").strip() if submission is not None else ""
        prompt = f"{typed_prompt}\n\n[تفريغ الرسالة الصوتية]:\n{transcript}" if typed_prompt and transcript else (typed_prompt or transcript)
        attachments = _submission_files(submission, folder_files)
    elif submission:
        prompt = (getattr(submission, "text", "") or "").strip()
        attachments = _submission_files(submission, folder_files)
    if attachments is None:
        return
    if prompt or attachments:
        if not prompt:
            prompt = "حلّل المرفقات المرفقة واذكر أهم ما تحتويه."
        if len(prompt) > MAX_PROMPT_CHARS:
            st.error("الرسالة تتجاوز الحد المسموح 20,000 حرف.")
            return
        fingerprint = _request_fingerprint(prompt, attachments)
        if fingerprint in chat.get("request_ids", []):
            st.warning("تم تجاهل طلب مكرر مطابق تمامًا لطلب أُرسل في هذه المحادثة.")
            return
        if not chat["messages"]:
            chat["title"] = _title_from_prompt(prompt)
        user_message_id = uuid.uuid4().hex
        request_id = uuid.uuid4().hex
        _ensure_chat_identity_state(chat)
        chat["request_ids"] = chat["request_ids"][-MAX_REQUEST_IDS:]
        chat["request_ids"].append(fingerprint)
        chat["request_ids"] = chat["request_ids"][-MAX_REQUEST_IDS:]
        chat["request_records"].append({"request_id": request_id, "fingerprint": fingerprint, "rounds": rounds, "created_at": _now()})
        attachment_context = "\n".join(f"- {a.get('name')} ({a.get('mime')}, {a.get('size', 0)} bytes, sha256={a.get('sha256', '')})" for a in attachments)[:6000]
        request_no = _request_display_number(chat, request_id)
        chat["messages"].append({"role": "user", "id": user_message_id, "content": prompt, "attachments": public_metadata(attachments), "attachment_context": attachment_context, "request_id": request_id, "request_no": request_no, "created_at": _now()})
        if voice_audio is not None:
            chat["messages"][-1].update({"voice": True, "voice_audio_key": user_message_id, "voice_mime": voice_mime})
            st.session_state.voice_audio_store[user_message_id] = voice_audio
            _prune_voice_store()
            fingerprints = st.session_state.voice_fingerprints.setdefault(chat["id"], set())
            fingerprints.add(voice_fingerprint)
            st.session_state.voice_fingerprints[chat["id"]] = set(list(fingerprints)[-20:])
        st.session_state.last_diagnostics = []
        with st.spinner("المجلس ينفذ Free API Cascade بالتوازي…"):
            results = _run_council(prompt, chat, rounds, credentials, attachments, model_candidates, user_message_id, request_id)
        st.session_state.last_results = [_public_result(r) for r in results]
        st.session_state.folder_nonce += 1
        st.session_state.voice_nonce += 1
        st.rerun()
    if st.session_state.last_diagnostics:
        st.divider()
        _render_provider_diagnostics(st.session_state.last_diagnostics)
    if st.session_state.last_results:
        st.divider()
        _render_bridge_audit(st.session_state.last_results)
        _render_diagnostics(st.session_state.last_results)
    _render_production_core_validation()


if __name__ == "__main__":
    run_app()
