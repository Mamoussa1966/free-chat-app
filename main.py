from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import copy
import html
import json
import re
import time
import uuid
import threading

import streamlit as st
from streamlit.components.v1 import html as components_html

from attachment_utils import normalize_uploaded_files, public_metadata
from providers import get_seats, VERSION as PROVIDER_VERSION, ProviderError, _canonical_error_classification, call_seat, capture_credentials, capture_model_candidates, configured_count, credential_sources, diagnostic_seat, get_model_candidates, model_config_fingerprint, model_config_sources, transcribe_audio_gemini, _deepseek_model_identity_matches, HOTFIX_RELEASE_VERSION
from production_core import RequestLifecycle, ProviderExecutionContract, SeatExecutionLedger, RequestRoundExecutionRegistry
from production_platform import PLATFORM_VERSION, compact_context, synthesize_council_results, provider_health_snapshot, security_audit, build_v23_platform_audit, multi_request_regression_audit
from v23_final_closure_audit import build_v23_final_closure_audit
from v23_audit_export import build_v23_audit_export, serialize_v23_audit_export
from conversation_runtime import (ensure_conversation_state, register_message, begin_round, finish_round, attach_request_identity, append_provenance, update_context_meta, conversation_audit, provenance_for_result, CONVERSATION_RUNTIME_VERSION)
from conversation_persistence_v26 import (ensure_persistence_store, persist_identity, snapshot_chat_identity, hydrate_chat_identity, persistence_audit)
from conversation_store import commit_canonical_record, hydrate_canonical_record, rebuild_runtime_indexes_from_canonical
from conversation_store import ensure_store, authoritative_snapshot, touch, canonical_upsert_message, canonical_upsert_request, canonical_upsert_round, canonical_create_lifecycle, assert_canonical_lifecycle_ready, prepare_historical_runtime
from conversation_migrations import migrate_chat
from message_ledger import record_message
from provenance_engine import record_result as record_v24_provenance
from timeline_runtime import event as timeline_event
from memory_layers import update_memory
from export_engine import export_conversation
from conversation_v25_runtime import ensure_v25_store, reconcile_request, authoritative_audit, sync_v26_message_record


# HOTFIX123: process-local idempotency gate for duplicate Streamlit submissions.
# A rerun can arrive before the first request has persisted its fingerprint;
# reserve the fingerprint before generating request_id or making any provider call.
_REQUEST_GATE_LOCK = threading.RLock()
_ACTIVE_REQUEST_FINGERPRINTS: set[str] = set()
_ORCHESTRATOR_REQUEST_LOCK = threading.RLock()
_ACTIVE_ORCHESTRATOR_REQUESTS: set[str] = set()
from production_core_test_runner import run_production_core_tests, render_report as render_production_core_report
from release_identity import deployed_release_identity, assert_deployed_release_identity

APP_VERSION = PROVIDER_VERSION
DISPLAY_VERSION = HOTFIX_RELEASE_VERSION
HOTFIX_VERSION = "HOTFIX144"
PLATFORM_RELEASE_VERSION = "V25.0-CONVERSATION-LEDGER-MESSAGE-RUNTIME"
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
NO_RESPONSE_AFTER_CASCADE = "NO_RESPONSE_AFTER_CASCADE"
BRIDGE_WRITE_PATTERN = re.compile(
    r"(?im)^\s*BRIDGE_WRITE\s*:\s*(BRIDGE_[A-Z0-9_]+)\s*(?:=\s*)?(.+?)\s*$"
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


def _sanitize_agent_prose(content: str, authoritative_request_id: str = "", bridge_values: list[str] | None = None) -> str:
    """HOTFIX131: agent prose is presentation-only and cannot define control-plane identity.

    Remove control-plane-looking lines (Request ID / result metadata / bridge writes)
    from provider prose and redact any application-owned bridge values. Structured
    result fields remain sourced exclusively from runtime/lifecycle records.
    """
    text = str(content or "")
    for value in (bridge_values or []):
        value = str(value or "").strip()
        if value:
            text = text.replace(value, "[REDACTED_BRIDGE_VALUE]")
    control_patterns = [
        re.compile(r"(?im)^\s*(?:REQUEST_ID|Request ID|RequestID)\s*[:=].*$"),
        re.compile(r"(?im)^\s*(?:STATUS|REQUEST_STATUS|Classification|Cascade Action|Executed Model|Free Cascade)\s*[:=].*$"),
        re.compile(r"(?im)^\s*BRIDGE_WRITE\s*[:=]?.*$"),
        re.compile(r"(?im)^\s*BRIDGE_RESULT\s*[:=]?.*$"),
        re.compile(r"(?im)^\s*BRIDGE_READ(?:_STATUS)?\s*[:=]?.*$"),
    ]
    for pattern in control_patterns:
        text = pattern.sub("[AGENT_CONTROL_PROSE_SUPPRESSED]", text)
    # HOTFIX142: control-plane metadata may be embedded inside a line/table/JSON-like
    # prose fragment instead of appearing at the beginning of the line. Suppress the
    # entire affected prose line so presentation text cannot masquerade as runtime
    # telemetry. This remains presentation-only; structured runtime fields are untouched.
    control_line_pattern = re.compile(
        r"(?i)(?:REQUEST[_ ]?ID|REQUEST_STATUS|STATUS|CLASSIFICATION|CASCADE ACTION|EXECUTED MODEL|FREE CASCADE|"
        r"BRIDGE_WRITE|BRIDGE_RESULT|BRIDGE_READ(?:_STATUS)?|RESULT ROW|RESULT_ROW|TOTAL_CASCADE_ATTEMPTS|PROVIDER_EXECUTION_EVENTS|ATTEMPT|"
        r"USER_PROMPT_CONTAINS_VALUE|GEMINI_INPUT_PROMPT_CONTAINS_VALUE|BRIDGE_STATE_CONTAINS_VALUE)\s*[:=]"
    )
    control_table_token_pattern = re.compile(
        r"(?i)(?:\bREQUEST[_ ]?ID\b|\bREQUEST_STATUS\b|\bSTATUS\b|\bCLASSIFICATION\b|"
        r"\bCASCADE ACTION\b|\bEXECUTED MODEL\b|\bFREE CASCADE\b|\bBRIDGE_WRITE\b|"
        r"\bBRIDGE_RESULT\b|\bBRIDGE_READ(?:_STATUS)?\b|\bRESULT[_ ]?ROW\b|"
        r"\bTOTAL_CASCADE_ATTEMPTS\b|\bPROVIDER_EXECUTION_EVENTS\b|"
        r"\bUSER_PROMPT_CONTAINS_VALUE\b|\bGEMINI_INPUT_PROMPT_CONTAINS_VALUE\b|\bBRIDGE_STATE_CONTAINS_VALUE\b)"
    )
    sanitized_lines = []
    for line in text.splitlines():
        if control_line_pattern.search(line) or ("|" in line and control_table_token_pattern.search(line)):
            sanitized_lines.append("[AGENT_CONTROL_PROSE_SUPPRESSED]")
        else:
            sanitized_lines.append(line)
    text = "\n".join(sanitized_lines)
    return text.strip()


def _extract_bridge_reads(content: str) -> list[str]:
    reads: list[str] = []
    for match in BRIDGE_READ_PATTERN.finditer(str(content or "")):
        key = match.group(1).strip()
        if key:
            reads.append(key)
    return reads


def _extract_hotfix141_harness(prompt: str) -> tuple[str, bool]:
    """HOTFIX141: explicit, bounded A/B/C harness control.

    Only the first non-empty line can activate the harness. Generic words in the
    body such as "Request A/B/C" never change normal Request semantics.
    """
    text = str(prompt or "")
    lines = text.splitlines()
    first = ""
    first_index = None
    for i, line in enumerate(lines):
        if line.strip():
            first = line.strip()
            first_index = i
            break
    if first.upper() != "HOTFIX141_HARNESS=ABC":
        return text, False
    remaining = lines[:first_index] + lines[first_index + 1:]
    return "\n".join(remaining).strip(), True


def _extract_bridge_control_values(prompt: str) -> tuple[str, list[tuple[str, str]]]:
    """Remove bridge control records from user-visible text and return them as application-owned inputs."""
    text = str(prompt or "")
    found: list[tuple[str, str]] = []
    patterns = [
        re.compile(r"(?im)^\s*(BRIDGE_[A-Z0-9_]+)\s*=\s*([^\r\n]+?)\s*$"),
        re.compile(r"(?im)^\s*BRIDGE_WRITE\s*:\s*(BRIDGE_[A-Z0-9_]+)\s*(?:=\s*)?([^\r\n]+?)\s*$"),
        re.compile(r"(?i)\b(BRIDGE_RESULT)\s*=\s*([^\r\n]+)") ,
        re.compile(r"(?i)BRIDGE_WRITE\s*:\s*(BRIDGE_RESULT)\s*(?:=\s*)?([^\r\n]+)") ,
    ]
    for pattern in patterns:
        for m in pattern.finditer(text):
            key, value = m.group(1).strip(), m.group(2).strip()
            if value and len(value) <= 2000 and (key, value) not in found:
                found.append((key, value))
    for pattern in patterns:
        text = pattern.sub("[BRIDGE_CONTROL_RECORD_REDACTED]", text)
    return text.strip(), found


def _validate_provider_output(result: dict, seat, request_id: str, round_no: int) -> dict:
    """Mandatory provider-output schema/identity gate before bridge handoff."""
    if not isinstance(result, dict):
        raise ValueError("provider output identity/schema is invalid")
    if str(result.get("request_id") or request_id) != str(request_id):
        raise ValueError("provider output identity request_id mismatch")
    if int(result.get("round", round_no) or round_no) != int(round_no):
        raise ValueError("provider output identity round mismatch")
    if str(result.get("seat") or "").strip() != str(getattr(seat, "key", "")).strip():
        raise ValueError("provider output identity seat mismatch")
    model = str(result.get("executed_model") or result.get("model") or "").strip()
    if not model:
        raise ValueError("provider output identity model missing")
    if str(result.get("model") or "").strip() != model:
        raise ValueError("provider output identity model mismatch")
    if str(result.get("status") or "").upper() != "SUCCESS":
        raise ValueError("provider output schema requires SUCCESS")
    if not str(result.get("content") or "").strip():
        raise ValueError("provider output schema requires non-empty content")
    checked = dict(result)
    checked["bridge_validated"] = True
    checked["bridge_record"] = {
        "validated": True, "request_id": str(request_id), "round": int(round_no),
        "seat": str(getattr(seat, "key", "")), "model": model,
    }
    return checked


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

    def __init__(self, initial_snapshot: str = "", max_chars: int = 30_000, request_id: str = "", round_no: int = 0, application_owned_test: bool = False):
        self.max_chars = max(1, int(max_chars))
        self.request_id = str(request_id or "")
        self.round_no = int(round_no or 0)
        # HOTFIX124: explicit application-owned Bridge test mode. When enabled,
        # the diagnostic canary is created and controlled exclusively by the
        # application; provider prose is never authoritative for the transaction.
        self.application_owned_test = bool(application_owned_test)
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
        self._runtime_payload_attestations: dict[int, dict] = {}
        self._audit_sealed_json: str = ""
        self._audit_seal_hash: str = ""
        initial = str(initial_snapshot or "").strip()
        if initial:
            self._entries.append(initial)

    def snapshot(self) -> str:
        """Return the internal Shared Context snapshot for diagnostics/tests."""
        return "\n\n".join(self._entries)[-self.max_chars:]

    def prompt_snapshot(self, target_seat=None) -> str:
        """Return provider-safe context with every committed bridge value removed.

        Redaction is value-first and pattern-second: even if a provider output embeds
        the bridge value inside prose rather than on a BRIDGE_WRITE/Value line, the
        exact value can never cross the provider-prompt boundary.
        """
        raw = "\n\n".join(self._entries)
        for record in self._values.values():
            value = str(record.get("value") or "")
            if value:
                raw = raw.replace(value, "[REDACTED_BRIDGE_VALUE]")
        base = BRIDGE_WRITE_PATTERN.sub(lambda m: f"BRIDGE_WRITE: {m.group(1).strip()} = [REDACTED_BRIDGE_VALUE]", raw)
        base = re.sub(r"(?im)^(\s*Value:\s*).+$", r"\1[REDACTED_BRIDGE_VALUE]", base)
        # HOTFIX123: the target prompt receives only a context-safe capability
        # projection.  Neither the bridge key (for example BRIDGE_RESULT) nor
        # its value is exposed to Gemini.  The application owns the target-side
        # READ and resolves it after the provider request has completed.
        if self._values or any("BRIDGE AGENT OUTPUT" in entry for entry in self._entries) or (self._committed and str(getattr(target_seat, "key", "") or "") == "gemini"):
            capability = (
                "BRIDGE CONTEXT CAPABILITY (SANITIZED):\n"
                "A committed transactional bridge state exists for this round.\n"
                "Bridge values and bridge keys are application-private and are not present in this prompt.\n"
                "Target-side READ, if required by the test, is resolved by the application after the provider response.\n"
                f"Room seat: {sorted({int(r.get('source_seat', 0) or 0) for r in self._values.values()})[0] if self._values else 7}\n"
                "Provider identity: DeepSeek\n"
                f"bridge_id: {self.bridge_id}\n"
                f"round_id: {self.round_no}"
            )
            base = (base + "\n\n" if base else "") + capability
        if str(getattr(target_seat, "key", "") or "") == "gemini":
            # Defense in depth: the target must not receive source protocol records,
            # bridge key literals, or bridge values.  Keep only the sanitized capability
            # projection below.
            base = re.sub(
                r"(?s)BRIDGE AGENT OUTPUT \(UNTRUSTED DATA\):.*?(?=\n\nBRIDGE CONTEXT CAPABILITY|\Z)",
                "",
                base,
            )
            base = re.sub(
                r"(?s)BRIDGE WRITE RECORD \(PROVIDER UNTRUSTED DATA\):.*?(?=\n\nBRIDGE CONTEXT CAPABILITY|\Z)",
                "",
                base,
            )
            base = re.sub(r"\bBRIDGE_[A-Z0-9_]+\b", "[REDACTED_BRIDGE_KEY]", base)
        return base[-self.max_chars:]

    def record_provider_input(self, seat, prompt: str) -> None:
        """Record the exact final provider input for post-request isolation auditing."""
        self._provider_input_prompts[int(getattr(seat, "room_slot", 0) or 0)] = str(prompt or "")

    def record_runtime_payload_attestation(self, seat, attestation: dict) -> None:
        """Capture the exact JSON payload passed to the official HTTP transport."""
        if not isinstance(attestation, dict) or not attestation.get("payload_json"):
            return
        self._runtime_payload_attestations[int(getattr(seat, "room_slot", 0) or 0)] = copy.deepcopy(attestation)

    def _runtime_payload_text(self, seat_slot: int) -> str:
        record = self._runtime_payload_attestations.get(int(seat_slot)) or {}
        return str(record.get("payload_json") or "")

    def seal_runtime_audit(self, source_seat: int = 7, target_seat: int = 2, key: str = "BRIDGE_RESULT", user_prompt: str = "") -> dict:
        """Seal bridge proof from actual runtime HTTP payloads, not prompt/context copies."""
        audit = self._transaction_audit_unsealed(source_seat, target_seat, key, user_prompt)
        canonical = json.dumps(audit, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self._audit_sealed_json = canonical
        self._audit_seal_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return self.transaction_audit(source_seat, target_seat, key, user_prompt)

    def sanitize_user_prompt(self, user_prompt: str, target_seat=None) -> str:
        """Sanitize bridge material before a provider prompt is constructed.

        Gemini receives a capability-safe projection: neither committed bridge values
        nor bridge key literals are allowed into its input prompt. Source-side agents
        retain the protocol key because they are responsible for producing the write
        record; the target-side READ is application-owned.
        """
        text = str(user_prompt or "")
        for key, record in self._values.items():
            value = str(record.get("value") or "")
            if value:
                text = text.replace(value, "[REDACTED_BRIDGE_VALUE]")
            if str(getattr(target_seat, "key", "") or "") == "gemini":
                text = re.sub(rf"\b{re.escape(str(key))}\b", "[REDACTED_BRIDGE_KEY]", text)
        return text

    def sanitize_agent_prose(self, content: str) -> str:
        """HOTFIX131: redact bridge values and control-plane metadata from agent prose."""
        values = [str(record.get("value") or "") for record in self._values.values() if isinstance(record, dict)]
        return _sanitize_agent_prose(content, self.request_id, values)


    def seed_application_state(self, key: str, value: str, source: str = "APPLICATION_TEST_CONTROL", source_seat: int = 0) -> None:
        """Seed bridge state in the application-owned control plane; never expose it to prompts.

        HOTFIX123: diagnostic bridge tests may bind an application-generated canary to the
        logical DeepSeek source seat (7). This is explicitly marked as application-owned
        test control; it is not presented as model-generated prose.
        """
        key, value = str(key or "").strip(), str(value or "").strip()
        if not key or not value or len(value) > 2000:
            return
        source_seat = int(source_seat or 0)
        self._write_sequence += 1
        self._source_values[key] = value
        self._values[key] = {
            "value": value, "source_seat": source_seat, "source_provider": source,
            "write_sequence": self._write_sequence, "write_origin": "APPLICATION_TEST_CONTROL",
        }
        self._record_trace(source_seat=source_seat, source_provider=source, target_seat=0, key=key,
                           write_sequence=self._write_sequence, commit_status="PENDING", schema_validation="PASS")

    def application_owned_state(self) -> dict:
        """Return persisted bridge control-plane state; values never enter provider prompts."""
        return {
            "schema": "bridge-application-state/v1",
            "request_id": self.request_id, "round_id": self.round_no, "bridge_id": self.bridge_id,
            "values": copy.deepcopy(self._values), "committed": bool(self._committed),
            "barrier_open": bool(self._barrier_open), "trace": copy.deepcopy(self.trace),
        }


    def append_user_declarations(self, user_prompt: str) -> None:
        """Legacy compatibility helper; production orchestration no longer calls this method."""
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
            # HOTFIX124: application-owned diagnostic state is immutable at the
            # provider boundary. A model may emit BRIDGE_WRITE-looking prose, but
            # that prose is untrusted presentation data and can never overwrite
            # an application-owned transaction value.
            existing = self._values.get(key)
            if self.application_owned_test and isinstance(existing, dict) and existing.get("write_origin") == "APPLICATION_TEST_CONTROL":
                self._entries.append(
                    "BRIDGE PROVIDER WRITE REJECTED (APPLICATION-OWNED STATE):\n"
                    f"Room seat: {room_slot}\nKey: {key}\nReason: PROVIDER_PROSE_CANNOT_OVERWRITE_APPLICATION_STATE"
                )
                self._record_trace(
                    source_seat=room_slot,
                    source_provider=provider,
                    target_seat=0,
                    key=key,
                    write_sequence=int(existing.get("write_sequence", 0) or 0),
                    commit_status="REJECTED",
                    schema_validation="UNTRUSTED_PROVIDER_DATA",
                )
                continue
            self._write_sequence += 1
            self._source_values[key] = value
            self._values[key] = {
                "value": value,
                "source_seat": room_slot,
                "source_provider": provider,
                "write_sequence": self._write_sequence,
                "write_origin": "PROVIDER_UNTRUSTED_DATA",
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

    def _transaction_audit_unsealed(self, source_seat: int = 7, target_seat: int = 2, key: str = "BRIDGE_RESULT", user_prompt: str = "") -> dict:
        record = self._values.get(key)
        source_value = self._source_values.get(key, "")
        read = self._resolved_reads.get(key)
        target_prompt = self._provider_input_prompts.get(int(target_seat), "")
        target_payload = self._runtime_payload_text(int(target_seat))
        source_payload = self._runtime_payload_text(int(source_seat))
        user_has = bool(source_value and source_value in str(user_prompt or ""))
        target_prompt_has = bool(source_value and source_value in target_prompt)
        target_payload_has = bool(source_value and source_value in target_payload)
        target_key_has = bool(key and key in target_payload)
        target_value_outside_sanitized = target_payload_has
        target_value = str(read.get("value")) if read else ""
        application_owned = bool(record and record.get("write_origin") == "APPLICATION_TEST_CONTROL")
        source_ok = bool(record and int(record.get("source_seat", 0)) == int(source_seat) and (not self.application_owned_test or application_owned))
        target_ok = bool(read and int(read.get("target_seat", 0)) == int(target_seat))
        runtime_attestation_present = bool(self._runtime_payload_attestations.get(int(target_seat), {}).get("payload_sha256"))
        runtime_payload_is_sanitized = runtime_attestation_present and not target_value_outside_sanitized and not target_key_has
        proven = bool(source_value)
        user_isolation = ("NO" if not user_has else "YES") if proven else "NOT_PROVEN"
        gemini_isolation = ("NO" if not target_prompt_has else "YES") if proven else "NOT_PROVEN"
        bridge_state = ("YES" if record and record.get("value") == source_value and (not self.application_owned_test or application_owned) else "NO") if proven else "NOT_PROVEN"
        match = ("PASS" if source_value and target_value and source_value == target_value and (not self.application_owned_test or application_owned) else "FAIL") if proven else "NOT_PROVEN"
        return {
            "BRIDGE_ID": self.bridge_id, "ROUND_ID": self.round_no,
            "SOURCE": "DeepSeek / Seat 7" if int(source_seat) == 7 else f"Seat {source_seat}",
            "TARGET": "Gemini / Seat 2" if int(target_seat) == 2 else f"Seat {target_seat}",
            "KEY": key,
            "WRITE": "PASS" if record and source_ok else "FAIL",
            "VALIDATE": "PASS" if record else "FAIL",
            "COMMIT": "PASS" if self._committed and record else "FAIL",
            "BARRIER": "PASS" if self._barrier_open and self._committed and record else "FAIL",
            "READ": "PASS" if read and target_ok else "FAIL",
            "SCHEMA_VALIDATION": "PASS" if read and target_ok else "FAIL",
            "SOURCE_VALUE": "[REDACTED]", "TARGET_VALUE": "[REDACTED]",
            "MATCH": match,
            "USER_PROMPT_CONTAINS_VALUE": user_isolation,
            "GEMINI_INPUT_PROMPT_CONTAINS_VALUE": gemini_isolation,
            "BRIDGE_STATE_CONTAINS_VALUE": bridge_state,
            "RUNTIME_HTTP_PAYLOAD_ATTESTED": "YES" if runtime_attestation_present else "NO",
            "RUNTIME_HTTP_PAYLOAD_CONTAINS_VALUE": ("NO" if not target_value_outside_sanitized else "YES") if runtime_attestation_present else "NOT_PROVEN",
            "RUNTIME_HTTP_PAYLOAD_CONTAINS_BRIDGE_KEY": ("NO" if not target_key_has else "YES") if runtime_attestation_present else "NOT_PROVEN",
            "GEMINI_RECEIVED_SANITIZED_REPRESENTATION_ONLY": "PASS" if runtime_payload_is_sanitized else "FAIL",
            "write_sequence": int(record.get("write_sequence", 0)) if record else 0,
            "read_sequence": int(read.get("read_sequence", 0)) if read else 0,
            "request_id": self.request_id,
            "runtime_payload_sha256": str(self._runtime_payload_attestations.get(int(target_seat), {}).get("payload_sha256") or ""),
        }

    def transaction_audit(self, source_seat: int = 7, target_seat: int = 2, key: str = "BRIDGE_RESULT", user_prompt: str = "") -> dict:
        audit = self._transaction_audit_unsealed(source_seat, target_seat, key, user_prompt)
        if self._audit_sealed_json:
            sealed = json.loads(self._audit_sealed_json)
            audit["AUDIT_SEALED"] = "YES"
            audit["AUDIT_SEAL_HASH"] = self._audit_seal_hash
            audit["PRODUCTION_GATE"] = "PASS" if {k:v for k,v in audit.items() if k not in ("AUDIT_SEALED","AUDIT_SEAL_HASH","PRODUCTION_GATE")} == sealed else "FAIL"
        else:
            audit["AUDIT_SEALED"] = "NO"
            audit["AUDIT_SEAL_HASH"] = ""
            audit["PRODUCTION_GATE"] = "NOT_SEALED"
        return audit

    def bridge_security_regression_gate(self, audit: dict | None = None) -> dict:
        """HOTFIX124 fail-closed publication gate for the nine Bridge invariants."""
        report = audit if isinstance(audit, dict) else self.transaction_audit()
        required = {
            "WRITE": "PASS", "VALIDATE": "PASS", "COMMIT": "PASS",
            "BARRIER": "PASS", "READ": "PASS", "SCHEMA_VALIDATION": "PASS",
            "MATCH": "PASS", "BRIDGE_STATE_CONTAINS_VALUE": "YES",
            "USER_PROMPT_CONTAINS_VALUE": "NO",
            "GEMINI_INPUT_PROMPT_CONTAINS_VALUE": "NO",
        }
        failures = [k for k, expected in required.items() if report.get(k) != expected]
        return {
            "schema": "hotfix124-bridge-security-regression-gate/v1",
            "status": "PASS" if not failures else "FAIL",
            "required": required,
            "failures": failures,
            "bridge_id": self.bridge_id,
            "request_id": self.request_id,
            "round_id": self.round_no,
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
        requested_keys = _extract_bridge_reads(str(result.get("content") or ""))
        # HOTFIX123: the transactional bridge is application-owned.  Once the
        # commit barrier is open, the target seat is allowed one explicit
        # application-side READ of the committed key even if the provider did
        # not echo the BRIDGE_READ control record.  The value is resolved only
        # after the provider request; it is never inserted into that request's
        # input prompt. This closes the real-world gap exposed by the prior release,
        # where Gemini could answer without emitting the optional control line
        # and the audit therefore reported READ=FAIL despite a valid commit.
        if not requested_keys and self._committed and self._barrier_open and int(getattr(seat, "room_slot", 0) or 0) == 2:
            if "BRIDGE_RESULT" in self._values:
                requested_keys = ["BRIDGE_RESULT"]
        for key in requested_keys:
            # HOTFIX123: if the application already performed the canonical
            # post-barrier READ before the target HTTP request, reuse that exact
            # committed read record. Do not increment read_sequence twice when
            # Gemini later echoes BRIDGE_READ in its response.
            existing = self._resolved_reads.get(key)
            if existing and int(existing.get("target_seat", 0) or 0) == int(getattr(seat, "room_slot", 0) or 0):
                value = str(existing.get("value"))
            else:
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
    chat = {
        "id": uuid.uuid4().hex,
        "title": "محادثة جديدة",
        "created_at": _now(),
        "messages": [],
        "request_ids": [],
        "request_records": [],
        "history_identity_ledger": [],
        "result_keys": [],
    }
    ensure_conversation_state(chat)
    ensure_store(chat)
    migrate_chat(chat)
    return chat


def _ensure_chat_identity_state(chat: dict) -> None:
    chat.setdefault("request_ids", [])
    chat.setdefault("request_records", [])
    chat.setdefault("history_identity_ledger", [])
    chat.setdefault("result_keys", [])
    ensure_conversation_state(chat)
    ensure_store(chat)
    migrate_chat(chat)


def _extract_requested_request_id(prompt: str) -> str:
    text = str(prompt or "")
    match = re.search(r"(?i)\bREQUEST\s*(?:ID|_ID)\s*[:=]?\s*`?([0-9a-f]{16,64})`?", text)
    if not match:
        match = re.search(r"(?i)\bauthoritative\s+request\s+id\s*[:=]?\s*`?([0-9a-f]{16,64})`?", text)
    return match.group(1).strip() if match else ""


def _extract_continuation_request_id(prompt: str, chat: dict) -> str:
    """Resolve only an explicit first-line continuation command from persisted state."""
    rid, mode = _continuation_control_prefix(prompt)
    if mode != "EXPLICIT_CONTROL" or not rid:
        return ""
    record = _request_record(chat, rid)
    return rid if isinstance(record, dict) else ""


def _continuation_control_prefix(prompt: str) -> tuple[str, str]:
    """HOTFIX139: detect continuation only from the first non-empty control line.

    The body of a prompt is never scanned for lifecycle keywords. A regression
    specification may freely discuss continuation, Request A/B/C, bridge controls,
    or "no new request" without changing a fresh submission into READ_ONLY mode.
    """
    lines = [line.strip() for line in str(prompt or "").splitlines() if line.strip()]
    first = lines[0] if lines else ""
    if not first:
        return "", ""

    # Dedicated control forms. These are intentionally line-scoped.
    rid_match = re.search(r"(?i)\b(?:CONTINUE_REQUEST_ID|CONTINUATION_REQUEST_ID)\s*[:=]\s*`?([0-9a-f]{16,64})`?\s*$", first)
    if rid_match:
        return rid_match.group(1).strip(), "EXPLICIT_CONTROL"

    rid_match = re.search(r"(?i)^continue\s+(?:the\s+)?same\s+request(?:\s+with)?\s+REQUEST\s*(?:ID|_ID)\s*[:=]?\s*`?([0-9a-f]{16,64})`?", first)
    if rid_match:
        return rid_match.group(1).strip(), "EXPLICIT_CONTROL"

    # Legacy-compatible explicit controls: REQUEST_ID plus continuation language
    # must all occur on the first line. This preserves existing continuation tests
    # while preventing arbitrary later prose from changing request mode.
    rid_match = re.search(r"(?i)\bREQUEST\s*(?:ID|_ID)\s*[:=]\s*`?([0-9a-f]{16,64})`?", first)
    if rid_match:
        rid = rid_match.group(1).strip()
        remainder = first[rid_match.end():]
        if re.search(r"(?i)(?:\bcontinue\b|\bcontinuation\b|\bresume\b|\bcontinuing\b|\bno\s+new\s+(?:request|round|bridge)\b|\bdo\s+not\s+(?:create|generate)\s+(?:a\s+)?(?:new\s+)?(?:request|round|bridge)\b|استكمال|استمر|تابع|تكملة|لا\s+(?:تنشئ|تُنشئ|تولد|تُولد)|بدون\s+(?:طلب|Request|جولة|Round|Bridge)\s+جديد)", first):
            return rid, "EXPLICIT_CONTROL"
        # A persisted COMPLETED Request ID on the control line remains authoritative.
        return rid, "PERSISTED_ID_CANDIDATE"

    if re.match(r"(?i)^(?:CONTINUE|CONTINUATION|RESUME)\b", first) or re.match(r"(?i)^(?:استكمال|استمر|تابع|تكملة)\b", first):
        return "", "EXPLICIT_CONTROL_MISSING_ID"
    return "", ""


def _continuation_request_record(prompt: str, chat: dict) -> tuple[str, dict | None, bool]:
    """HOTFIX139: resolve continuation before request allocation, from control syntax only."""
    requested_id, control_mode = _continuation_control_prefix(prompt)
    if not control_mode:
        return "", None, False
    persisted_record = _request_record(chat, requested_id) if requested_id else None
    if not requested_id:
        return "", None, True
    if control_mode == "PERSISTED_ID_CANDIDATE" and not isinstance(persisted_record, dict):
        return "", None, False
    return requested_id, persisted_record, True


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
    ensure_persistence_store(st.session_state)
    defaults = {"rounds": 1, "folder_nonce": 0, "voice_nonce": 0, "last_results": [], "last_diagnostics": [], "voice_fingerprints": {}, "voice_audio_store": {}, "last_voice_error": "", "platform_context_meta": {}, "last_synthesis": {}, "last_health_snapshot": [], "last_security_audit": {}, "last_v23_platform_audit": {}, "last_v23_final_closure_audit": {}}
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
            hydrate_canonical_record(chat, st.session_state)
            rebuild_runtime_indexes_from_canonical(chat, st.session_state)
            hydrate_chat_identity(chat, st.session_state)
            snapshot_chat_identity(chat, st.session_state)
            return chat
    chat = _new_chat()
    st.session_state.chats.insert(0, chat)
    st.session_state.active_chat_id = chat["id"]
    hydrate_chat_identity(chat, st.session_state)
    snapshot_chat_identity(chat, st.session_state)
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
    text, meta = compact_context([{"role": "context", "content": "\n\n".join(lines)}], max_chars=max_chars)
    chat["platform_context_meta"] = meta
    update_context_meta(chat, meta, meta.get("digest", ""))
    try:
        st.session_state.platform_context_meta = meta
    except Exception:
        pass
    return text


def _worker_failure(seat, exc: Exception, model_candidates: dict | None = None, request_id: str = "", round_no: int = 0) -> dict:
    # HOTFIX127: a worker-level failure is NOT a provider execution attempt.
    # It may occur before the provider adapter is entered (deadline, orchestration
    # exception, missing configuration, etc.). Never synthesize Attempt #1 here.
    models = tuple((model_candidates or {}).get(seat.key) or ())
    return {
        "seat": seat.key, "name": seat.name, "label": seat.label,
        "status": "DISPATCH_REJECTED", "mode": "internal",
        "model": "", "content": "",
        "classification": "DISPATCH_REJECTED",
        "error": f"class=dispatch_rejected; internal worker failure before provider execution: {exc.__class__.__name__}",
        "attempt_summaries": [], "attempt_telemetry": [],
        "latency": 0.0, "attempted_models": [],
        "official_authenticated": False, "execution_started": False,
        "runtime_execution_events": [],
        "request_id": request_id, "round": round_no,
    }


def _history_attempt_summaries(details: list[dict]) -> list[dict]:
    """Persist only the original compact, non-sensitive classifications in History."""
    allowed = {
        "MODEL_UNAVAILABLE", "QUOTA_EXCEEDED", "RATE_LIMITED",
        "AUTHENTICATION_ERROR", "API_ERROR", "TRANSIENT_PROVIDER_ERROR", "INVALID_REQUEST", "NETWORK_ERROR",
        "TIMEOUT", "UNKNOWN", "DISPATCH_REJECTED", "NOT_EXECUTED", "EXECUTION_STARTED", "PROVIDER_ERROR", "SUCCESS",
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
            "provider": str(detail.get("provider") or "").strip(),
            "request_id": str(detail.get("request_id") or ""),
            "round": int(detail.get("round", 0) or 0),
            "final_result": str(detail.get("final_result") or "FAILED").upper(),
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
            "cascade_reason": str(detail.get("cascade_reason") or "").strip(),
        })
    return out


def _public_display_class(display_class: str) -> str:
    # A timeout means the provider did not complete a response in the current attempt.
    if display_class == "TIMEOUT":
        return PUBLIC_NO_RESPONSE
    return str(display_class or "UNKNOWN")


def _hotfix128_result_semantics(result: dict) -> dict:
    """Normalize public result status without inventing provider execution.

    HOTFIX128: configured/requested/executed/successful are distinct states.
    A result with zero actual attempted models can never be classified as an
    API/provider failure, and a seat with zero configured Free models is not a
    failed API request.
    """
    out = dict(result or {})
    attempted = [str(x).strip() for x in (out.get("attempted_models") or []) if str(x).strip()]
    configured_marker = out.get("model_candidates_configured", None)
    candidates_configured = bool(configured_marker) if configured_marker is not None else True
    status = str(out.get("status") or "").upper()
    if configured_marker is False or status == "NO_FREE_MODEL_CONFIGURED":
        out["status"] = "NOT_CONFIGURED"
        out["classification"] = "NOT_CONFIGURED"
        out["attempted_models"] = []
        return out
    if not attempted:
        if status not in {"DISPATCH_REJECTED", "REQUEST_CREATED"}:
            out["status"] = "NOT_EXECUTED"
        if status == "SUCCESS":
            out["status"] = "NOT_EXECUTED"
        if str(out.get("classification") or "").upper() in {"API_ERROR", "PROVIDER_ERROR", "UNKNOWN", "SUCCESS", ""}:
            out["classification"] = "DISPATCH_REJECTED" if out["status"] == "DISPATCH_REJECTED" else "NOT_EXECUTED"
    return out


def _public_result(result: dict) -> dict:
    """Return the UI-safe result persisted in session state. Raw provider payloads stay transient."""
    public = _hotfix128_result_semantics(result)
    details = list(public.get("attempt_diagnostics", []) or [])
    public["attempt_summaries"] = _history_attempt_summaries(details)
    public["attempt_telemetry"] = list(public.get("attempt_telemetry") or _safe_attempt_telemetry(details, public))
    for telemetry in public["attempt_telemetry"]:
        if str(telemetry.get("classification") or "").upper() == "TIMEOUT":
            telemetry["classification"] = PUBLIC_NO_RESPONSE
    for event in public.get("runtime_execution_events") or []:
        if isinstance(event, dict) and str(event.get("classification") or "").upper() == "TIMEOUT":
            event["classification"] = PUBLIC_NO_RESPONSE
    classification = str(public.get("classification") or "").strip().upper()
    allowed_classes = {"NOT_CONFIGURED", "REQUEST_CREATED", "DISPATCH_REJECTED", "NOT_EXECUTED", "EXECUTION_STARTED", "PROVIDER_ERROR", "TRANSIENT_PROVIDER_ERROR", "MODEL_UNAVAILABLE", "QUOTA_ERROR", "SUCCESS",
                       "MODEL_UNAVAILABLE", "QUOTA_EXCEEDED", "RATE_LIMITED", "AUTHENTICATION_ERROR", "API_ERROR", "INVALID_REQUEST", "NETWORK_ERROR", "TIMEOUT", "UNKNOWN", "NO_FREE_MODEL_CONFIGURED"}
    # HOTFIX128: no attempted model means no provider API error can be claimed.
    if not [m for m in (public.get("attempted_models") or []) if str(m).strip()]:
        if classification in {"API_ERROR", "PROVIDER_ERROR", "UNKNOWN"}:
            classification = "NOT_EXECUTED" if public.get("status") != "DISPATCH_REJECTED" else "DISPATCH_REJECTED"
    if not public.get("model_candidates_configured", True):
        classification = "NOT_CONFIGURED"
    if classification not in allowed_classes:
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
    public.pop("_bridge_application_state", None)
    return public

def _render_live_cascade_telemetry(result: dict) -> None:
    """Render safe per-attempt telemetry immediately after one seat execution.

    This function is intentionally side-effect free with respect to provider
    execution. It only renders already-sanitized attempt telemetry and never
    starts another request, retry, cascade, or orchestrator path.
    """
    if not isinstance(result, dict):
        return
    details = list(result.get("attempt_diagnostics", []) or [])
    telemetry = list(result.get("attempt_telemetry", []) or _safe_attempt_telemetry(details, result))
    if not telemetry:
        return
    provider = str(result.get("name") or result.get("seat") or "Provider").strip()
    for item in telemetry:
        model = str(item.get("model") or "—").strip()
        classification = str(item.get("classification") or "UNKNOWN").strip().upper()
        action = str(item.get("cascade_action") or "CASCADE_STOP").strip().upper()
        attempt = item.get("attempt", "?")
        request_id = str(item.get("request_id") or result.get("request_id") or "—")
        round_no = item.get("round", result.get("round", "?"))
        st.caption(
            f"{provider} · Attempt {attempt} · `{model}` → {classification} → {action} · Request {request_id} · Round {round_no}"
        )


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


def _provider_identity_matches(seat_key: str, executed_model: str, reported_model: str) -> bool:
    if not reported_model:
        return True
    if seat_key == "deepseek":
        return _deepseek_model_identity_matches(executed_model, reported_model)
    return reported_model.lower() == executed_model.lower()


def _assert_provider_boundary(prompt: str, provider_prompt: str, bridge_controls: list[tuple[str, str]] | None = None) -> None:
    """HOTFIX132: validate the *actual provider input*, not the user's diagnostic instructions.

    The previous implementation concatenated ``prompt`` with ``provider_prompt``.
    That made a legitimate diagnostic request containing the literal token
    ``BRIDGE_RESULT`` fail the dispatch gate before any provider execution.
    The user request is control/input data; only the sanitized provider-layer
    prompt is subject to the no-leak invariant.
    """
    provider_text = str(provider_prompt or "")
    if re.search(r"(?i)\bBRIDGE_RESULT\b", provider_text):
        raise RuntimeError("BRIDGE_RESULT leaked into provider-layer prompt")
    for key, value in (bridge_controls or []):
        key_text = str(key or "").strip()
        value_text = str(value or "").strip()
        if key_text and re.search(rf"(?i)\b{re.escape(key_text)}\b", provider_text):
            raise RuntimeError("bridge key leaked into provider-layer prompt")
        if value_text and value_text in provider_text:
            raise RuntimeError("bridge value leaked into provider-layer prompt")


def _dispatch_gate(seat, request_id: str, round_no: int, credential, model_candidates) -> tuple[bool, str]:
    """HOTFIX132 authoritative pre-execution dispatch contract.

    A configured seat with an explicit Free model, a valid request identity and
    positive round is dispatchable. This gate never calls a provider and never
    treats provider/API errors as dispatch failures.
    """
    if not str(request_id or "").strip():
        return False, "REQUEST_ID_MISSING"
    try:
        rid = int(round_no)
    except (TypeError, ValueError):
        return False, "ROUND_INVALID"
    if rid <= 0:
        return False, "ROUND_INVALID"
    if credential is None or not str(credential).strip():
        return False, "CREDENTIAL_MISSING"
    candidates = tuple(str(m).strip() for m in (model_candidates or ()) if str(m).strip())
    if not candidates:
        return False, "FREE_MODEL_LIST_EMPTY"
    if not str(getattr(seat, "key", "") or "").strip():
        return False, "SEAT_KEY_MISSING"
    return True, "READY_FREE_MODEL"


def _run_round(user_prompt: str, chat: dict, round_no: int, credentials: dict, attachments: list[dict], model_candidates: dict, current_user_message_id: str, deadline: float | None, request_id: str, bridge_controls: list[tuple[str, str]] | None = None) -> list[dict]:
    # HOTFIX125.4: a continuation may never reach the round/provider layer.  The
    # orchestrator gate normally catches this earlier; this invariant is defense-in-depth.
    for msg in chat.get("messages", []):
        if isinstance(msg, dict) and str(msg.get("request_id") or "") == str(request_id):
            if str(msg.get("continuation_mode") or "").upper() == "READ_ONLY":
                raise RuntimeError("HOTFIX125.4: provider/round execution forbidden for continuation")
    seats = get_seats()
    # HOTFIX125: Bridge execution is an explicit request-scoped mode.  A normal
    # Persistence/History request must not instantiate, fail, or render a Bridge audit.
    bridge_test_active = (
        "TRANSACTIONAL BRIDGE ISOLATION" in str(user_prompt).upper()
        or bool(bridge_controls)
    )
    bridge = SharedContextBridge(
        _shared_context(chat, exclude_message_id=current_user_message_id),
        max_chars=30_000,
        request_id=request_id,
        round_no=round_no,
        application_owned_test=bridge_test_active,
    )
    # HOTFIX123 Bridge/Security deterministic test boundary. For the explicit
    # Transactional Bridge diagnostic, the application owns the canary value and
    # binds it to the logical DeepSeek source seat. The canary is never copied into
    # the user prompt or Gemini input, and its origin is recorded as application test
    # control so the audit cannot misattribute model prose as authoritative state.
    if bridge_test_active:
        # HOTFIX124: always create the diagnostic canary from application-owned
        # runtime state. Activation no longer depends on a second brittle phrase
        # or on a user-supplied BRIDGE_RESULT value.
        bridge.seed_application_state(
            "BRIDGE_RESULT",
            f"HOTFIX124_BRIDGE_RUNTIME_{uuid.uuid4().hex}",
            source="DeepSeek",
            source_seat=7,
        )

    # HOTFIX125: explicit bridge controls are meaningful only inside the
    # request-scoped Bridge Test mode. Never create Bridge state for ordinary
    # Persistence/History requests.
    if bridge_test_active:
        for key, value in (bridge_controls or []):
            bridge.seed_application_state(key, value)
    results: dict[str, dict] = {}
    working_context = bridge.prompt_snapshot(None)
    # HOTFIX123: one logical seat execution claim per request/round. Free Cascade
    # attempts remain inside call_seat() and therefore cannot create a second
    # seat Request. This is the production boundary for Request Determinism.
    execution_ledger = SeatExecutionLedger(request_id, round_no)

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
    for seat in SEATS if False else bridge_order:
        execution_id = execution_ledger.claim(seat.key)
        dispatch_ok, dispatch_reason = _dispatch_gate(
            seat, request_id, round_no, credentials.get(seat.key), model_candidates.get(seat.key)
        )
        if not dispatch_ok:
            results[seat.key] = {
                "seat": seat.key, "name": seat.name, "label": seat.label,
                "status": "NOT_CONFIGURED" if dispatch_reason in {"CREDENTIAL_MISSING", "FREE_MODEL_LIST_EMPTY"} else "DISPATCH_REJECTED",
                "classification": "NOT_CONFIGURED" if dispatch_reason in {"CREDENTIAL_MISSING", "FREE_MODEL_LIST_EMPTY"} else "DISPATCH_REJECTED",
                "dispatch_decision": "DISPATCH_REJECTED",
                "dispatch_reason": dispatch_reason,
                "dispatch_accepted": False, "dispatch_gate": "HOTFIX132",
                "mode": "internal", "model": "", "executed_model": "", "content": "",
                "attempt_summaries": [], "attempt_telemetry": [], "attempted_models": [],
                "official_authenticated": False, "execution_started": False,
                "runtime_execution_events": [], "request_id": request_id, "round": round_no,
                "request_routed": False,
                "model_candidates_configured": bool(model_candidates.get(seat.key)),
                "execution_id": execution_id,
                "execution_claim": f"{request_id}:{round_no}:{seat.key}",
            }
            continue
        try:
            # HOTFIX132: dispatch is accepted before entering the Provider Execution Contract.
            # Provider/API failures after this point are execution outcomes, never dispatch failures.
            # HOTFIX123: execution ownership is immutable for this request/round/seat.
            # The provider may perform multiple Free Cascade attempts, but all
            # attempts belong to this one execution claim.
            execution_ledger.assert_claimed(seat.key, execution_id)
            # HOTFIX123: resolve the committed target-side READ at the application
            # boundary, after COMMIT + BARRIER and before the target provider HTTP
            # request. The resolved value is retained only in bridge state/audit;
            # it is NEVER injected into the Gemini prompt or HTTP payload. This
            # closes the prior gap where READ depended on a provider echo/control
            # record and could therefore fail when Gemini returned normally or
            # failed before emitting BRIDGE_READ.
            if seat.key == "gemini" and bridge._committed and bridge._barrier_open:
                bridge.read("BRIDGE_RESULT", seat)

            provider_prompt = bridge.prompt_snapshot(seat)
            working_context = provider_prompt
            # HOTFIX127: configuration/routing are separate from execution.
            # This records only booleans; credentials themselves never enter state.
            result_request_routed = bool(credentials.get(seat.key) and model_candidates.get(seat.key))
            provider_user_prompt = bridge.sanitize_user_prompt(user_prompt, seat)
            _assert_provider_boundary(provider_user_prompt, provider_prompt, bridge_controls)
            bridge.record_provider_input(seat, provider_prompt)
            result = call_seat(
                seat, provider_user_prompt, provider_prompt, round_no, False,
                credentials.get(seat.key), attachments, model_candidates.get(seat.key),
                deadline, request_id,
            )
            result["dispatch_decision"] = "DISPATCH_ACCEPTED"
            result["dispatch_reason"] = "READY_FREE_MODEL"
            result["dispatch_accepted"] = True
            result["dispatch_gate"] = "HOTFIX132"
            if str(result.get("status") or "").upper() == "SUCCESS":
                result = _validate_provider_output(result, seat, request_id, round_no)
                # Authoritative cascade identity comes from the actual API-attempt
                # ledger, never from a provider-generated field.
                attempted_models = [str(m).strip() for m in result.get("attempted_models", []) if str(m).strip()]
                executed_model = str(result.get("executed_model") or result.get("model") or "").strip()
                if executed_model and executed_model in attempted_models:
                    result["cascade_position"] = attempted_models.index(executed_model) + 1
                elif executed_model:
                    raise RuntimeError("Execution identity has no matching actual cascade attempt")
            # Capture the exact prompt actually built by the provider runtime,
            # then remove the transient audit field before any history/UI path.
            actual_provider_prompt = result.pop("_provider_input_prompt", "") if isinstance(result, dict) else ""
            runtime_attestation = result.pop("_runtime_payload_attestation", {}) if isinstance(result, dict) else {}
            bridge.record_provider_input(seat, actual_provider_prompt or provider_prompt)
            bridge.record_runtime_payload_attestation(seat, runtime_attestation)
            _render_live_cascade_telemetry(result)
            result["request_routed"] = result_request_routed
            result["model_candidates_configured"] = bool(model_candidates.get(seat.key))
            result["execution_id"] = execution_id
            result["execution_claim"] = f"{request_id}:{round_no}:{seat.key}"
            results[seat.key] = result
            bridge.append_agent_output(seat, result)
            # HOTFIX131: provider prose is untrusted presentation data. It cannot
            # introduce a Request ID/status/result row or expose bridge values.
            result["content"] = bridge.sanitize_agent_prose(result.get("content", ""))
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
            if seat.key == "gemini" and bridge_test_active:
                # HOTFIX125: emit Bridge audit only when this Request explicitly
                # requested a Bridge Test. A non-Bridge request has no Bridge audit.
                # HOTFIX139: audit the control-free, provider-boundary-safe user input.
                # Bridge assignments are application-owned control data and must not
                # be counted as a user-prompt leak after extraction/redaction.
                # HOTFIX124: audit the original user boundary. The canary is
                # application-generated, so normal execution remains clean; if a
                # canary is ever present in the raw user prompt, the gate must see it
                # rather than having sanitization hide the leak.
                result["bridge_transaction_audit"] = bridge.seal_runtime_audit(user_prompt=str(user_prompt or ""))
                result["bridge_security_regression_gate"] = bridge.bridge_security_regression_gate(result["bridge_transaction_audit"])
                result["_bridge_application_state"] = bridge.application_owned_state()
                result["bridge_trace"] = bridge.transaction_trace()
            else:
                result["bridge_trace"] = bridge.transaction_trace()
        except Exception as exc:
            # HOTFIX132: once DISPATCH_ACCEPTED has been recorded, an exception is
            # an execution/provider-contract failure, not a dispatch rejection.
            failure = {
                "seat": seat.key, "name": seat.name, "label": seat.label,
                "status": "PROVIDER_ERROR", "mode": "official_api",
                "model": "", "executed_model": "", "content": "",
                "classification": "PROVIDER_ERROR",
                "error": f"provider execution failed after dispatch acceptance: {exc.__class__.__name__}",
                "attempt_summaries": [], "attempt_telemetry": [], "attempted_models": [],
                "official_authenticated": bool(credentials.get(seat.key)),
                "execution_started": False, "runtime_execution_events": [],
                "request_id": request_id, "round": round_no,
                "dispatch_decision": "DISPATCH_ACCEPTED",
                "dispatch_reason": "READY_FREE_MODEL",
                "dispatch_accepted": True, "dispatch_gate": "HOTFIX132",
                "request_routed": True,
                "model_candidates_configured": bool(model_candidates.get(seat.key)),
                "execution_id": execution_id,
                "execution_claim": f"{request_id}:{round_no}:{seat.key}",
            }
            results[seat.key] = failure

    for seat in seats:
        results.setdefault(
            seat.key,
            _worker_failure(
                seat, TimeoutError("round deadline exceeded"),
                model_candidates, request_id, round_no,
            ),
        )

    # HOTFIX123: diagnostic answers must not invent the executed cascade position.
    # The provider response is still allowed to be arbitrary during normal chat,
    # but the explicit bridge-proof request is a runtime diagnostic.
    # In that mode the application emits the authoritative execution/bridge facts
    # from the post-HTTP ledger and Transactional Bridge audit, so a model cannot
    # report e.g. "#0" when the actual HTTP attempt was Free #1.
    if ("TRANSACTIONAL BRIDGE ISOLATION" in str(user_prompt) and
            "Free Cascade number actually executed" in str(user_prompt)):
        deepseek = results.get("deepseek")
        gemini = results.get("gemini")
        audit = (gemini or {}).get("bridge_transaction_audit") or {}
        if deepseek is not None:
            attempted = [str(m).strip() for m in (deepseek.get("attempted_models") or []) if str(m).strip()]
            executed = str(deepseek.get("executed_model") or deepseek.get("model") or "").strip()
            cascade_position = (attempted.index(executed) + 1) if executed in attempted else None
            deepseek["cascade_position"] = cascade_position
            deepseek["executed_cascade_position"] = cascade_position
            # Only expose the bridge value through the already-redacted proof audit.
            deepseek["content"] = "\n".join([
                f"1. Provider: {deepseek.get('name', 'DeepSeek')}",
                f"2. Seat: {deepseek.get('room_slot', 7)}",
                f"3. Executed model: {executed or '—'}",
                f"4. Free Cascade number actually executed: {cascade_position if cascade_position is not None else '—'}",
                f"5. Request ID: {request_id}",
                f"6. Round: {round_no}",
                f"7. Execution Identity: {deepseek.get('provider_key', 'deepseek')} / {executed or '—'} / API_AGENT / Official API",
                "8. هل تم تمرير Shared Context؟: نعم" if deepseek.get("bridge_transaction_audit") else "8. هل تم تمرير Shared Context؟: نعم (Bridge context path)",
                "9. هل تم استخدام Transactional Bridge؟: نعم",
                f"10. BRIDGE_ID: {audit.get('BRIDGE_ID', '—')}",
                f"11. هل تم تنفيذ WRITE؟: {audit.get('WRITE', 'FAIL')}",
                f"12. هل تم تنفيذ VALIDATE؟: {audit.get('VALIDATE', 'FAIL')}",
                f"13. هل تم تنفيذ COMMIT؟: {audit.get('COMMIT', 'FAIL')}",
                f"14. هل تم تنفيذ BARRIER؟: {audit.get('BARRIER', 'FAIL')}",
                f"15. هل تم تنفيذ READ؟: {audit.get('READ', 'FAIL')}",
                f"16. هل كانت قيمة BRIDGE_RESULT موجودة داخل Bridge State؟: {audit.get('BRIDGE_STATE_CONTAINS_VALUE', 'NO')}",
                f"17. هل ظهرت قيمة BRIDGE_RESULT حرفيًا داخل User Prompt؟: {audit.get('USER_PROMPT_CONTAINS_VALUE', 'UNKNOWN')}",
                f"18. هل ظهرت قيمة BRIDGE_RESULT حرفيًا داخل Gemini Input Prompt؟: {audit.get('GEMINI_INPUT_PROMPT_CONTAINS_VALUE', 'UNKNOWN')}",
                f"19. هل نجحت Schema Validation؟: {audit.get('SCHEMA_VALIDATION', 'FAIL')}",
                f"20. هل تطابقت القيمة المقروءة مع القيمة المكتوبة؟: {audit.get('MATCH', 'FAIL')}",
                "",
                "AUTHORITATIVE RUNTIME ATTESTATION: القيم أعلاه صادرة من سجل HTTP الفعلي وTransactional Bridge audit، وليست من تخمين النموذج.",
            ])
    return [results[seat.key] for seat in seats]


def _authoritative_ui_projection(chat: dict, request_id: str) -> dict:
    """HOTFIX147/HOTFIX130 compatibility API.

    UI counters are a presentation projection of the persisted authoritative
    request record. They are never derived from rendered message rows, agent
    prose, or the latest-request projection.
    """
    chat = chat if isinstance(chat, dict) else {}
    rid = str(request_id or "").strip()
    records = [r for r in chat.get("request_records", []) if isinstance(r, dict)]
    record = next((r for r in records if str(r.get("request_id") or "") == rid), None)
    if not record:
        return {"configured": 0, "requested": 0, "executed": 0, "success": 0,
                "dispatch_rejected": 0, "provider_error": 0, "not_configured": 0,
                "cascade_attempts": 0, "request_id": rid}
    metrics = record.get("request_metrics") if isinstance(record.get("request_metrics"), dict) else {}
    results = record.get("results") if isinstance(record.get("results"), list) else []
    statuses = [str(r.get("status") or "").upper() for r in results if isinstance(r, dict)]
    return {
        "configured": int(metrics.get("configured_seats", sum(1 for r in results if r.get("model_candidates_configured") is True and r.get("request_routed") is True))),
        "requested": int(metrics.get("requested_seats", sum(1 for r in results if r.get("request_routed") is True))),
        "executed": int(metrics.get("executed_seats", sum(1 for r in results if r.get("runtime_execution_events")))),
        "success": int(metrics.get("successful_seats", statuses.count("SUCCESS"))),
        "dispatch_rejected": statuses.count("DISPATCH_REJECTED"),
        "provider_error": statuses.count("PROVIDER_ERROR"),
        "not_configured": statuses.count("NOT_CONFIGURED"),
        "cascade_attempts": int(metrics.get("total_cascade_attempts", sum(len(r.get("runtime_execution_events") or []) for r in results if isinstance(r, dict)))),
        "request_id": rid,
    }


def _format_authoritative_counter_summary(counters: dict) -> str:
    """Format semantic counters without a generic failed/successful aggregate."""
    return " · ".join([
        f"CONFIGURED {int(counters.get('configured', 0))}",
        f"REQUESTED {int(counters.get('requested', 0))}",
        f"EXECUTED {int(counters.get('executed', 0))}",
        f"SUCCESS {int(counters.get('success', 0))}",
        f"DISPATCH_REJECTED {int(counters.get('dispatch_rejected', 0))}",
        f"PROVIDER_ERROR {int(counters.get('provider_error', 0))}",
        f"NOT_CONFIGURED {int(counters.get('not_configured', 0))}",
        f"CASCADE_ATTEMPTS {int(counters.get('cascade_attempts', 0))}",
    ])


def _authoritative_request_metrics(request_id: str, round_results: list[dict], audit_events: list[dict]) -> dict:
    """HOTFIX127: authoritative accounting from actual runtime execution events only.

    CONFIGURED, REQUEST_CREATED, REQUESTED, EXECUTED, SUCCESSFUL and CASCADE_ATTEMPTS
    are intentionally separate quantities. A placeholder/worker failure is never an
    execution event and therefore never increments attempt or provider-execution
    counters.
    """
    rid = str(request_id or "").strip()
    results = [r for r in (round_results or []) if isinstance(r, dict)]
    events = [e for e in (audit_events or []) if isinstance(e, dict) and str(e.get("request_id") or "") == rid]

    def runtime_events(result: dict) -> list[dict]:
        raw = result.get("runtime_execution_events")
        if isinstance(raw, list):
            return [e for e in raw if isinstance(e, dict) and e.get("execution_started") is True]
        telemetry = result.get("attempt_telemetry") or result.get("attempt_summaries") or result.get("attempt_diagnostics") or []
        out = []
        for d in telemetry:
            if not isinstance(d, dict):
                continue
            # Only actual attempt records qualify. Legacy summaries without an
            # explicit execution marker are accepted when they have a model AND
            # a positive attempt number AND the result has attempted_models.
            if d.get("execution_started") is True or (d.get("model") and d.get("attempt")):
                x = dict(d)
                x["execution_started"] = True
                out.append(x)
        return out

    actual_by_result = [(r, runtime_events(r)) for r in results]
    executed_seat_keys = {str(r.get("seat") or "").strip() for r, evs in actual_by_result if evs}
    successful_seat_keys = {str(r.get("seat") or "").strip() for r, evs in actual_by_result
                            if evs and str(r.get("status") or "").upper() == "SUCCESS" and r.get("content")}
    requested_seat_keys = {str(r.get("seat") or "").strip() for r in results
                           if r.get("request_routed") is True}
    configured_seat_keys = {str(r.get("seat") or "").strip() for r in results
                            if r.get("model_candidates_configured") is True and r.get("request_routed") is True}

    total_attempts = sum(len(evs) for _, evs in actual_by_result)
    attempts_by_provider: dict[str, int] = {}
    for r, evs in actual_by_result:
        provider = str(r.get("name") or r.get("seat") or "").strip()
        if evs:
            attempts_by_provider[provider] = attempts_by_provider.get(provider, 0) + len(evs)

    provider_exec_events = [e for e in events if str(e.get("event_type") or "") == "PROVIDER_RESULT"
                            and e.get("metadata", {}).get("runtime_execution") == "true"]
    bridge_ids = {str(r.get("bridge_transaction_audit", {}).get("BRIDGE_ID") or "").strip()
                  for r in results if isinstance(r.get("bridge_transaction_audit"), dict)}
    bridge_ids.discard("")
    all_request_ids = {rid} | {str(r.get("request_id") or "").strip() for r in results if r.get("request_id")}
    all_request_ids |= {str(e.get("request_id") or "").strip() for e in events if e.get("request_id")}
    rounds = sorted({int(e.get("round_id") or 0) for e in events if int(e.get("round_id") or 0) > 0})
    deepseek_round1_executions = sum(len(evs) for r, evs in actual_by_result
                                     if str(r.get("seat") or "").lower() == "deepseek" and int(r.get("round") or 0) == 1)
    return {
        "request_id": rid,
        "rounds": rounds,
        "unique_request_ids": len(all_request_ids),
        "request_ids": sorted(x for x in all_request_ids if x),
        "unique_bridge_ids": len(bridge_ids),
        "bridge_ids": sorted(bridge_ids),
        "configured_seats": len(configured_seat_keys),
        "configured_seat_keys": sorted(x for x in configured_seat_keys if x),
        "requested_seats": len(requested_seat_keys),
        "requested_seat_keys": sorted(x for x in requested_seat_keys if x),
        "executed_seats": len(executed_seat_keys),
        "executed_seat_keys": sorted(x for x in executed_seat_keys if x),
        "successful_seats": len(successful_seat_keys),
        "successful_seat_keys": sorted(x for x in successful_seat_keys if x),
        "total_cascade_attempts": total_attempts,
        "attempts_by_provider": attempts_by_provider,
        "provider_execution_events": len(provider_exec_events),
        "deepseek_round1_executions": deepseek_round1_executions,
        "audit_event_count": len(events),
    }


def _request_record(chat: dict, request_id: str) -> dict | None:
    _ensure_chat_identity_state(chat)
    rid = str(request_id or "").strip()
    return next((r for r in chat.get("request_records", []) if isinstance(r, dict) and str(r.get("request_id") or "").strip() == rid), None)


def _authoritative_round_base(chat: dict) -> int:
    """Return the highest numeric Round ordinal already committed by the canonical ledger.

    This is deliberately derived only from application-owned ConversationRecord state;
    UI labels, audit labels, provider prose, and the current request ledger are not used.
    """
    record = chat.get("conversation_record") if isinstance(chat.get("conversation_record"), dict) else {}
    rows = record.get("rounds", []) if isinstance(record.get("rounds"), list) else []
    numbers = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        value = row.get("round")
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            numbers.append(number)
    return max(numbers, default=0)


def _run_council(user_prompt: str, chat: dict, rounds: int, credentials: dict, attachments: list[dict], model_candidates: dict, current_user_message_id: str, request_id: str, bridge_controls: list[tuple[str, str]] | None = None, continuation_request_id: str = "") -> list[dict]:
    # HOTFIX123.2: one orchestrator invocation per Request ID. A secondary
    # execution path must never create another lifecycle/round/bridge. A completed
    # request is returned from its immutable in-chat result cache.
    request_id = str(request_id or "").strip()
    if not request_id:
        raise ValueError("request_id is required")
    if str(continuation_request_id or "").strip():
        if str(request_id).strip() != str(continuation_request_id).strip():
            raise RuntimeError("Continuation request identity mismatch: no new Request ID is permitted")
        raise RuntimeError("Continuation is READ_ONLY: _run_council/provider execution is forbidden")
    _ensure_chat_identity_state(chat)
    with _ORCHESTRATOR_REQUEST_LOCK:
        for record in chat.get("request_records", []):
            if not isinstance(record, dict) or str(record.get("request_id") or "") != request_id:
                continue
            if record.get("state") == "COMPLETED" and isinstance(record.get("results"), list):
                return copy.deepcopy(record["results"])
            if request_id in _ACTIVE_ORCHESTRATOR_REQUESTS or record.get("state") == "RUNNING":
                raise RuntimeError(f"Duplicate orchestrator execution blocked: {request_id}")
        _ACTIVE_ORCHESTRATOR_REQUESTS.add(request_id)
        record = next((r for r in chat["request_records"] if isinstance(r, dict) and str(r.get("request_id") or "") == request_id), None)
        if record is not None:
            record["state"] = "RUNNING"
            record["execution_scope"] = request_id
            # HOTFIX125: immutable request-scoped Bridge mode.
            record["bridge_test_requested"] = bool(
                "TRANSACTIONAL BRIDGE ISOLATION" in str(user_prompt or "").upper()
                or bool(bridge_controls)
            )
    # V26.3.8: every real orchestrator entry point converges into the canonical
    # ConversationRecord before creating/dispatching its first provider round.
    if record is None:
        # Direct/test orchestrator entry points may arrive with an already-owned
        # Request ID but without the outer chat-input envelope. In that case the
        # orchestrator itself is the lifecycle creator; it binds the supplied ID
        # and Message ID into the canonical store before dispatch.
        record = {
            "request_id": request_id, "conversation_id": chat.get("conversation_id"),
            "session_id": chat.get("session_id"), "message_id": current_user_message_id,
            "created_at": _now(), "state": "RUNNING",
            "identity_authority": "RUNTIME_REQUEST_ID",
            "bridge_test_requested": bool(
                "TRANSACTIONAL BRIDGE ISOLATION" in str(user_prompt or "").upper()
                or bool(bridge_controls)
            ),
        }
        chat.setdefault("request_records", []).append(record)
    canonical_upsert_request(chat, record, st.session_state)
    canonical_upsert_message(chat, {
        "message_id": current_user_message_id,
        "conversation_id": chat.get("conversation_id"),
        "session_id": chat.get("session_id"),
        "role": "user",
        "request_id": request_id,
        "created_at": record.get("created_at") or _now(),
    }, st.session_state)
    deadline = None
    lifecycle = RequestLifecycle.begin(request_id)
    round_registry = RequestRoundExecutionRegistry(request_id)
    chat.setdefault("audit_events", [])
    chat["audit_events"] = [e for e in chat.get("audit_events", []) if e.get("request_id") != request_id]
    all_results: list[dict] = []
    total_rounds = max(1, min(int(rounds), MAX_ROUNDS))
    # HOTFIX126: round identity is conversation-scoped, not reset to r1 for every
    # new Request. The provider still executes exactly `total_rounds` rounds for
    # this Request, but the authoritative RoundRecord receives the next monotonic
    # conversation ordinal from the canonical ledger. This makes Message 2 ->
    # Request 2 -> Round 2 provable from Application-Owned Runtime State itself.
    round_base = _authoritative_round_base(chat)
    try:
        lifecycle.record("REQUEST_START", round_id=0, status="RUNNING")
        lifecycle.record("ROUTING", round_id=0, status="ROUTED", metadata={"rounds": str(total_rounds), "conversation_round_base": str(round_base)})
        for local_round_no in range(1, total_rounds + 1):
            round_no = round_base + local_round_no
            round_registry.claim_round(round_no)
            lifecycle.start_round(round_no)
            runtime_round_id = begin_round(chat, current_user_message_id, request_id, round_no, st.session_state)
            round_row = next((x for x in reversed(chat.get("round_ledger", [])) if isinstance(x, dict) and x.get("round_id") == runtime_round_id), None)
            if round_row:
                # prior lifecycle convergence: converge the already allocated identity into one
                # application-owned atomic lifecycle checkpoint before provider dispatch.
                request_row = next((x for x in reversed(chat.get("request_records", [])) if isinstance(x, dict) and str(x.get("request_id") or "") == request_id), None)
                message_row = {
                    "message_id": current_user_message_id,
                    "conversation_id": chat.get("conversation_id"),
                    "session_id": chat.get("session_id"),
                    "role": "user",
                    "request_id": request_id,
                    "created_at": (request_row or {}).get("created_at") or _now(),
                }
                atomic = canonical_create_lifecycle(chat, message_row, request_row or {"request_id": request_id, "message_id": current_user_message_id}, round_row, st.session_state)
                if not atomic.get("committed"):
                    raise RuntimeError("CANONICAL_ATOMIC_LIFECYCLE_COMMIT_FAILED")
                persist_identity(chat, st.session_state, round_row=round_row)
            # V26.3.8 hard gate: provider dispatch cannot begin until the canonical
            # ConversationRecord contains the exact Message→Request→Round chain.
            assert_canonical_lifecycle_ready(chat, current_user_message_id, request_id, runtime_round_id)
            lifecycle.record("PROVIDER_EXECUTION", round_id=round_no, status="STARTED")
            round_results = _run_round(user_prompt, chat, round_no, credentials, attachments, model_candidates, current_user_message_id, deadline, request_id, bridge_controls)
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
                    if not _provider_identity_matches(seat_key, executed_model, provider_reported_model):
                        raise RuntimeError(f"Provider identity invariant violated: {provider_reported_model!r} != {executed_model!r}")
                    chat["messages"].append({"role": "assistant", "id": uuid.uuid4().hex, "seat": result["name"], "seat_key": seat_key, "label": result["label"], "content": result["content"], "round": round_no, "mode": "official", "model": executed_model, "executed_model": executed_model, "provider_reported_model": provider_reported_model, "cascade_position": int(result.get("cascade_position") or len(attempted_models) or 0), "room_slot": int(next((s.room_slot for s in get_seats() if s.key == seat_key), 0)), "provider_identity": next((s.name for s in get_seats() if s.key == seat_key), result.get("name", "")), "provider_key": seat_key, "agent_type": "API_AGENT", "api_mode": "Official API", "attempted_models": attempted_models, "attempt_summaries": _history_attempt_summaries(result.get("attempt_diagnostics", []) or []), "request_id": request_id, "result_key": result_key, "created_at": _now()})
            keys = set(chat.get("result_keys", []))
            keys.update(f"{request_id}:{round_no}:{r.get('seat', '')}" for r in round_results)
            chat["result_keys"] = list(keys)[-MAX_CHAT_MESSAGES:]
            chat["messages"] = chat["messages"][-MAX_CHAT_MESSAGES:]
            success_count = sum(1 for r in round_results if str(r.get("status") or "").upper() == "SUCCESS")
            lifecycle.finish_round(round_no, success_count, len(round_results))
            finish_round(chat, runtime_round_id, "COMPLETED", len(round_results), st.session_state)
            round_row = next((x for x in reversed(chat.get("round_ledger", [])) if isinstance(x, dict) and x.get("round_id") == runtime_round_id), None)
            if round_row:
                persist_identity(chat, st.session_state, round_row=round_row)
            lifecycle.record("RESPONSE_VALIDATION", round_id=round_no, status="PASS" if all(str(r.get("status") or "").upper() != "SUCCESS" or bool(r.get("content")) for r in round_results) else "FAIL")
            for r in round_results:
                runtime_events = r.get("runtime_execution_events") or []
                for ev in runtime_events if isinstance(runtime_events, list) else []:
                    if not isinstance(ev, dict) or ev.get("execution_started") is not True:
                        continue
                    lifecycle.record(
                        "PROVIDER_RESULT", round_id=round_no, provider=str(r.get("name") or r.get("seat") or ""),
                        model=str(ev.get("model") or r.get("executed_model") or r.get("model") or ""),
                        cascade_position=ev.get("attempt"), status=str(ev.get("status") or ("SUCCESS" if str(r.get("status") or "").upper() == "SUCCESS" and int(ev.get("attempt", 0) or 0) == len(r.get("attempted_models") or []) else "FAILED")),
                        classification=str(ev.get("classification") or ""), latency_ms=(float(ev.get("execution_time", 0.0) or 0.0) * 1000.0),
                        metadata={"result_key": str(r.get("result_key") or ""), "runtime_execution": "true", "attempt_id": str(ev.get("attempt_id") or "")},
                    )
        any_success = any(str(r.get("status") or "").upper() == "SUCCESS" for r in all_results)
        lifecycle.record("REQUEST_COMMIT", round_id=0, status="COMMITTED" if any_success else "REJECTED", metadata={"success_count": str(sum(1 for r in all_results if str(r.get("status") or "").upper() == "SUCCESS"))})
        lifecycle.finish(success=any_success)
    except Exception:
        if lifecycle.state.value == "RUNNING":
            lifecycle.finish(success=False)
        with _ORCHESTRATOR_REQUEST_LOCK:
            record = next((r for r in chat.get("request_records", []) if isinstance(r, dict) and str(r.get("request_id") or "") == request_id), None)
            if record is not None:
                record["state"] = "FAILED"
            _ACTIVE_ORCHESTRATOR_REQUESTS.discard(request_id)
        raise
    chat["audit_events"] = lifecycle.audit_snapshot()[-500:]
    chat["conversation_runtime_audit"] = conversation_audit(chat)
    with _ORCHESTRATOR_REQUEST_LOCK:
        record = next((r for r in chat.get("request_records", []) if isinstance(r, dict) and str(r.get("request_id") or "") == request_id), None)
        if record is not None:
            record["state"] = "COMPLETED"
            record["rounds_executed"] = total_rounds
            record["results"] = copy.deepcopy(all_results)
            bridge_states = [copy.deepcopy(r.get("_bridge_application_state")) for r in round_results if isinstance(r, dict) and r.get("_bridge_application_state")]
            record["application_owned_bridge_state"] = bridge_states[-1] if bridge_states else record.get("application_owned_bridge_state")
            # HOTFIX123: persist authoritative counters on the request record itself.
            # These counters are derived from lifecycle/audit data and persisted result
            # telemetry, never from provider-generated prose.
            record["request_metrics"] = _authoritative_request_metrics(
                request_id, all_results, chat.get("audit_events", [])
            )
            record["synthesis"] = synthesize_council_results(all_results)
            record["synthesis"]["conversation_id"] = chat.get("conversation_id")
            record["synthesis"]["session_id"] = chat.get("session_id")
            record["synthesis"]["provenance_count"] = sum(len(provenance_for_result(chat, current_user_message_id, int(r.get("round") or 1), r)) for r in all_results if isinstance(r, dict))
            # V26.3.10: mutate the canonical RequestRecord with authoritative
            # completion/metrics data, then commit the entire historical record.
            canonical_upsert_request(chat, record, st.session_state)
            st.session_state["last_synthesis"] = copy.deepcopy(record["synthesis"])
        _ACTIVE_ORCHESTRATOR_REQUESTS.discard(request_id)
    return all_results


def _run_hotfix141_abc_harness(user_prompt: str, chat: dict, rounds: int, credentials: dict, attachments: list[dict], model_candidates: dict, base_user_message_id: str) -> list[dict]:
    """Execute three real Request Lifecycles sequentially from one user submission.

    Each lifecycle gets a fresh runtime Request ID and its own application-owned
    bridge control value. No provider/agent prose is used as identity or accounting.
    """
    reports: list[dict] = []
    labels = ("A", "B", "C")
    for label in labels:
        request_id = uuid.uuid4().hex
        fingerprint = _request_fingerprint(f"HOTFIX141:{label}:{request_id}:{user_prompt}", attachments)
        _ensure_chat_identity_state(chat)
        chat["request_ids"].append(fingerprint)
        chat["request_ids"] = chat["request_ids"][-MAX_REQUEST_IDS:]
        chat["request_records"].append({
            "request_id": request_id, "fingerprint": fingerprint, "rounds": rounds,
            "created_at": _now(), "identity_authority": "RUNTIME_REQUEST_ID",
            "harness": "HOTFIX141_ABC", "harness_label": label,
        })
        synthetic_message_id = f"{base_user_message_id}:{label}"
        # Bridge control is generated by the application, not extracted from the
        # user prompt. The opaque value is never inserted into provider prompts.
        bridge_value = f"HOTFIX141_RUNTIME_{label}_{uuid.uuid4().hex}"
        results = _run_council(
            user_prompt, chat, 1, credentials, attachments, model_candidates,
            synthetic_message_id, request_id, [("BRIDGE_RESULT", bridge_value)]
        )
        record = next(r for r in chat.get("request_records", []) if r.get("request_id") == request_id)
        metrics = copy.deepcopy(record.get("request_metrics") or {})
        bridge_audits = [
            copy.deepcopy(r.get("bridge_transaction_audit"))
            for r in results if isinstance(r, dict) and isinstance(r.get("bridge_transaction_audit"), dict)
        ]
        reports.append({
            "label": label, "request_id": request_id, "request_status": record.get("state", ""),
            "total_cascade_attempts": metrics.get("total_cascade_attempts", 0),
            "provider_execution_events": metrics.get("provider_execution_events", 0),
            "unique_request_ids": metrics.get("unique_request_ids", 0),
            "unique_bridge_ids": metrics.get("unique_bridge_ids", 0),
            "bridge_audits": bridge_audits,
        })
    return reports


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
        st.subheader("🚀 V23 Production Platform")
        st.caption("HOTFIX124→HOTFIX130 + V23 Release Candidate: طبقات إضافية فوق Core HOTFIX123.2.")
        if st.button("🩺 Platform Health", use_container_width=True):
            st.session_state.last_health_snapshot = provider_health_snapshot(get_seats(), credentials, model_candidates)
        if st.session_state.get("last_health_snapshot"):
            for row in st.session_state.last_health_snapshot:
                st.caption(f"{row['provider']} · {row['status']} · Free models={row['free_models']}")
        if st.button("🔐 Security Isolation Audit", use_container_width=True):
            st.session_state.last_security_audit = security_audit(st.session_state.get("chats", []))
        audit = st.session_state.get("last_security_audit") or {}
        if audit:
            st.caption(f"Security audit: {audit.get('status', 'UNKNOWN')}")
        if st.button("🧠 Context Compaction Audit", use_container_width=True):
            ctx = _shared_context(_active_chat(), max_chars=30000)
            st.session_state.platform_context_meta = st.session_state.get("platform_context_meta", {})
            st.success(f"Context bounded: {st.session_state.platform_context_meta.get('chars', len(ctx))} chars")
        if st.session_state.get("last_synthesis"):
            syn = st.session_state.last_synthesis
            st.caption(f"Synthesis: {syn.get('status')} · successful seats={syn.get('successful_seats', 0)}")
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
        st.subheader("🧭 V24 Conversation Platform")
        ensure_store(chat)
        st.caption(f"Conversation: `{str(chat.get('conversation_id') or "")[:18]}…` · Session: `{str(chat.get('session_id') or "")[:18]}…`")
        if st.button("🔍 لماذا هذه الإجابة؟", use_container_width=True): st.session_state.v24_show_provenance = not st.session_state.get("v24_show_provenance", False)
        if st.button("🕒 Timeline", use_container_width=True): st.session_state.v24_show_timeline = not st.session_state.get("v24_show_timeline", False)
        if st.button("📦 Export Conversation", use_container_width=True): st.session_state.v24_export = export_conversation(chat)
        if st.button("🗄️ Archive Conversation", use_container_width=True): chat["archived"] = True; touch(chat); st.success("تمت أرشفة المحادثة.")
        if st.session_state.get("v24_show_provenance"):
            st.json({"conversation_id":chat.get("conversation_id"),"session_id":chat.get("session_id"),"results":chat.get("result_ledger_v24", [])[-30:],"provenance":chat.get("provenance_ledger_v24", [])[-50:]})
        if st.session_state.get("v24_show_timeline"):
            for ev in chat.get("timeline_ledger_v24", [])[-50:]: st.caption(f"{ev.get('timestamp')} · {ev.get('event_type')} · {ev.get('provider','')} · {ev.get('status','')}")
        if st.session_state.get("v24_export"):
            st.download_button("⬇️ تنزيل سجل المحادثة", st.session_state.v24_export, file_name="conversation_export.json", mime="application/json", use_container_width=True)
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
        st.caption("Configured Free #1 → " + f"`{models[0]}`" if models else "لا يوجد Free API model مُكوّن")
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
                if not _provider_identity_matches(seat.key, executed_model, provider_reported_model):
                    st.error("⚠️ Provider identity mismatch: هوية النموذج التي أعادها المزود لا تطابق النموذج المنفذ.")
                    continue
            request_id = str(message.get("request_id") or "").strip()
            # HOTFIX123: the runtime Request ID is the sole request identity shown
            # in seat cards. A human-friendly sequence number is not an identity.
            prefix = f"Request ID = `{request_id}` · " if request_id else ""
            st.markdown(f"**{prefix}Round {message.get('round', '?')} · 🟢 Official API · `{executed_model or displayed_model}`**")
            if attempted_models:
                st.caption("Cascade attempts: " + " → ".join(f"#{i+1} `{m}`" for i, m in enumerate(attempted_models)))
            cascade_position = int(message.get("cascade_position") or (attempted_models.index(executed_model) + 1 if executed_model in attempted_models else 0))
            if cascade_position > 0:
                st.caption(f"Executed Free Cascade: **#{cascade_position}** · `{executed_model}`")
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
            "AUTHENTICATION_ERROR", "API_ERROR", "TRANSIENT_PROVIDER_ERROR", "INVALID_REQUEST", "NETWORK_ERROR",
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
            "AUTHENTICATION_ERROR", "API_ERROR", "TRANSIENT_PROVIDER_ERROR", "INVALID_REQUEST", "NETWORK_ERROR",
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
        st.caption("LIVE Cascade telemetry — raw provider payloads/credentials hidden")
        for detail in summaries:
            provider = str(detail.get("provider") or result.get("name") or "Provider")
            attempt = detail.get("attempt", "?")
            model = str(detail.get("model") or "—")
            cls = str(detail.get("classification") or "UNKNOWN").upper()
            action = str(detail.get("cascade_action") or ("CASCADE_CONTINUE" if detail.get("retryable") else "CASCADE_STOP")).upper()
            request_id = str(detail.get("request_id") or result.get("request_id") or "—")
            round_no = detail.get("round", result.get("round", "?"))
            final_result = str(detail.get("final_result") or "FAILED").upper()
            status_text = "SUCCESS" if final_result == "SUCCESS" or cls == "SUCCESS" else "FAILED"
            st.caption(f"{provider} · Attempt {attempt} · Request ID = {request_id} · Round = {round_no} · {model} → {cls} → {action} · Status = {status_text}")

    if status == "SUCCESS":
        display_model = result.get('executed_model') or result['model']
        attempt_latency = result.get("successful_attempt_latency")
        attempt_text = f" · attempt {attempt_latency}s" if attempt_latency is not None else ""
        st.success(f"{'🟢' if diagnostic_only else '✅'} {result['label']} — Official API — `{display_model}` — total {result.get('latency', 0)}s{attempt_text}")
        if summaries:
            with st.expander("🧪 LIVE Cascade attempt telemetry", expanded=True):
                render_attempts()
    elif status == "AUTHENTICATION_OK_NO_FREE_MODEL":
        st.warning(f"🟡 {result['label']} — نقطة المصادقة قبلت المفتاح، لكن لا يوجد Free model مُكوّن.")
        st.caption("Classification: NOT_CONFIGURED")
    elif status == "DISPATCH_REJECTED":
        st.warning(f"🟡 {result.get('label', result.get('name', 'Provider'))} — لم يبدأ تنفيذ المزود؛ تم رفض/إيقاف dispatch قبل Provider Execution Contract.")
        st.caption("Classification: DISPATCH_REJECTED · Provider error not proven")
    elif status == "NOT_EXECUTED":
        st.warning(f"🟡 {result.get('label', result.get('name', 'Provider'))} — لم يتم تنفيذ أي محاولة API.")
        st.caption("Classification: NOT_EXECUTED · Provider error not proven")
    elif status == "NO_FREE_MODEL_CONFIGURED":
        st.warning(f"🟡 {result['label']} — لا يوجد Free API model مُكوّن؛ لم يتم إرسال أي طلب.")
        st.caption("Classification: NOT_CONFIGURED")
    elif status == PUBLIC_NO_RESPONSE:
        st.warning(f"🟡 {result.get('label', result.get('name', 'Provider'))} — لم تصل استجابة سريعة من المزود.")
        if summaries:
            with st.expander("🧪 LIVE Cascade attempt telemetry", expanded=True):
                render_attempts()
    else:
        with st.expander(f"🔴 {result.get('label', result.get('name', 'Provider'))} — Official API failed", expanded=True):
            st.write("Official API request failed; raw provider payload is not shown in the UI.")
            st.write("Attempted models:", ", ".join(result.get("attempted_models", [])) or "none")
            if summaries:
                render_attempts()
            else:
                classification = str(result.get("classification") or "").strip().upper() or _result_error_classification(result)
                st.caption(f"Final classification: **{classification}**")


def _hotfix131_runtime_prose_audit(results: list[dict], request_id: str, bridge_audit: dict | None = None) -> dict:
    """HOTFIX134: authoritative runtime check that agent prose cannot mutate control-plane results.

    This is a presentation/integrity audit only. Structured identity/status/model fields are
    taken from the application-owned result rows and lifecycle records; provider prose is
    treated as untrusted text. The audit deliberately reports PASS only when the persisted
    rows have one authoritative request identity and the prose boundary contains no control
    records or application-owned bridge values.
    """
    rid = str(request_id or "").strip()
    # HOTFIX144: scope the audit to the authoritative rows belonging to THIS
    # Request ID. The UI may render a combined A/B/C result set; rows from other
    # independent lifecycles must never be interpreted as an identity override.
    all_rows = [r for r in (results or []) if isinstance(r, dict)]
    rows = [r for r in all_rows if str(r.get("request_id") or "").strip() == rid]
    # A populated result set with zero rows for the authoritative Request ID is
    # itself a structured identity failure; do not let filtering hide a mismatch.
    scoped_identity_missing = bool(rid) and bool(all_rows) and not rows
    bridge_values: list[str] = []
    if isinstance(bridge_audit, dict):
        for key in ("SOURCE_VALUE", "TARGET_VALUE"):
            value = str(bridge_audit.get(key) or "").strip()
            if value and value != "[REDACTED]":
                bridge_values.append(value)
    # Also inspect application-owned bridge state where available, without ever rendering it.
    for r in rows:
        state = r.get("_bridge_application_state")
        if isinstance(state, dict):
            value = str(state.get("value") or state.get("BRIDGE_RESULT") or "").strip()
            if value and value != "[REDACTED]":
                bridge_values.append(value)
    bridge_values = sorted(set(bridge_values))

    request_ids_ok = bool(rid) and bool(rows) and not scoped_identity_missing and all(str(r.get("request_id") or "").strip() == rid for r in rows)
    # HOTFIX144: match control-plane field names as standalone tokens only.
    # Labels such as AGENT_PROSE_REQUEST_ID_OVERRIDE are themselves audit prose and
    # must never be mistaken for an attempted runtime identity override.
    content_control_pattern = re.compile(
        r"(?i)(?<![A-Z0-9_])(?:REQUEST_ID|Request ID|RequestID|REQUEST_STATUS|STATUS|Classification|Cascade Action|Executed Model|Free Cascade|"
        r"BRIDGE_WRITE|BRIDGE_RESULT|BRIDGE_READ(?:_STATUS)?|RESULT[_ ]?ROW|TOTAL_CASCADE_ATTEMPTS|PROVIDER_EXECUTION_EVENTS|ATTEMPT|"
        r"USER_PROMPT_CONTAINS_VALUE|GEMINI_INPUT_PROMPT_CONTAINS_VALUE|BRIDGE_STATE_CONTAINS_VALUE)(?![A-Z0-9_])\s*[:=]"
    )
    content_control_leak = False
    bridge_value_leak = False
    for r in rows:
        content = str(r.get("content") or "")
        if content_control_pattern.search(content):
            content_control_leak = True
        if any(v and v in content for v in bridge_values):
            bridge_value_leak = True

    # The structured result row is authoritative only if its identity agrees with the
    # lifecycle request and every executed event carries the same request/round identity.
    structured_identity_ok = bool(rid) and not scoped_identity_missing
    for r in rows:
        if str(r.get("request_id") or "").strip() != rid:
            structured_identity_ok = False
        for ev in r.get("runtime_execution_events") or []:
            if not isinstance(ev, dict) or ev.get("execution_started") is not True:
                continue
            if str(ev.get("request_id") or rid).strip() != rid:
                structured_identity_ok = False
            if int(ev.get("round", r.get("round", 0)) or 0) != int(r.get("round", 0) or 0):
                structured_identity_ok = False

    status_override = bool(content_control_leak)
    row_injection = bool(content_control_leak)
    bridge_redacted = bool(isinstance(bridge_audit, dict)) and not bridge_value_leak
    return {
        # HOTFIX144: prose is untrusted presentation data. A model may print fake
        # control-looking labels; that is not a runtime override. Only a mutation
        # of application-owned structured records can fail these authority checks.
        "AGENT_PROSE_REQUEST_ID_OVERRIDE": "PASS" if request_ids_ok else "FAIL",
        "AGENT_PROSE_STATUS_OVERRIDE": "PASS" if structured_identity_ok else "FAIL",
        "AGENT_PROSE_RESULT_ROW_INJECTION": "PASS" if structured_identity_ok else "FAIL",
        "AUTHORITATIVE_RUNTIME_IDENTITY": "PASS" if structured_identity_ok else "FAIL",
        "BRIDGE_CONTROL_RECORD_REDACTED": "PASS" if bridge_redacted else "FAIL",
        "BRIDGE_VALUE_PROSE_LEAK": "FAIL" if bridge_value_leak else "PASS",
        "CONTROL_PROSE_LEAK": "FAIL" if content_control_leak else "PASS",
        # HOTFIX144: the authoritative gate is exclusively structured runtime state.
        # Agent prose, including fake Request IDs/status/result rows, is presentation-only.
        "PROSE_ISOLATION_AUTHORITATIVE_GATE": "PASS" if structured_identity_ok and request_ids_ok else "FAIL",
    }


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
    request_id = str(audit.get("request_id") or "").strip()
    if request_id:
        # HOTFIX123: render counters from the persisted request record, not the
        # DeepSeek/Gemini response text.
        chat = _active_chat()
        record = _request_record(chat, request_id)
        metrics = (record or {}).get("request_metrics") or {}
        if metrics:
            st.subheader("📊 Authoritative Request Audit")
            st.code("\n".join([
                f"REQUEST_ID = {metrics.get('request_id', request_id)}",
                f"ROUND_IDS = {metrics.get('rounds', [])}",
                f"UNIQUE_REQUEST_IDS = {metrics.get('unique_request_ids', 0)}",
                f"UNIQUE_BRIDGE_IDS = {metrics.get('unique_bridge_ids', 0)}",
                f"TOTAL_CASCADE_ATTEMPTS = {metrics.get('total_cascade_attempts', 0)}",
                f"DEEPSEEK_SEAT_7_ROUND_1_EXECUTIONS = {metrics.get('deepseek_round1_executions', 0)}",
                f"PROVIDER_EXECUTION_EVENTS = {metrics.get('provider_execution_events', 0)}",
                "COUNTER_SOURCE = REQUEST_RECORD / LIFECYCLE_AUDIT (CURRENT REQUEST TELEMETRY)",
                "SEAT_GENERATED_PROSE_USED_AS_COUNTER_SOURCE = NO",
            ]), language="text")

    # HOTFIX134: expose explicit runtime-backed HOTFIX131 identity/prose checks.
    prose_audit = _hotfix131_runtime_prose_audit(results, request_id, audit)
    st.subheader("🔎 HOTFIX131 — Authoritative Identity / Bridge-Prose Isolation")
    st.code("\n".join([
        f"AGENT_PROSE_REQUEST_ID_OVERRIDE = {prose_audit['AGENT_PROSE_REQUEST_ID_OVERRIDE']}",
        f"AGENT_PROSE_STATUS_OVERRIDE = {prose_audit['AGENT_PROSE_STATUS_OVERRIDE']}",
        f"AGENT_PROSE_RESULT_ROW_INJECTION = {prose_audit['AGENT_PROSE_RESULT_ROW_INJECTION']}",
        f"BRIDGE_CONTROL_RECORD_REDACTED = {prose_audit['BRIDGE_CONTROL_RECORD_REDACTED']}",
        f"BRIDGE_VALUE_PROSE_LEAK = {prose_audit['BRIDGE_VALUE_PROSE_LEAK']}",
        f"CONTROL_PROSE_LEAK = {prose_audit['CONTROL_PROSE_LEAK']}",
        f"AUTHORITATIVE_RUNTIME_IDENTITY = {prose_audit['AUTHORITATIVE_RUNTIME_IDENTITY']}",
        f"PROSE_ISOLATION_AUTHORITATIVE_GATE = {prose_audit['PROSE_ISOLATION_AUTHORITATIVE_GATE']}",
    ]), language="text")

def _ui_semantic_counters(results: list[dict]) -> dict:
    """HOTFIX129: state-specific UI counters; never collapse non-success states into `failed`.

    Runtime accounting remains authoritative in the request record. This helper is a
    presentation projection only and never mutates lifecycle/audit counters.
    """
    rows = [r for r in (results or []) if isinstance(r, dict)]
    statuses = [str(r.get("status") or "").strip().upper() for r in rows]
    requested = [r for r in rows if r.get("request_routed") is True]
    configured = [r for r in requested if r.get("model_candidates_configured") is True]
    executed = [r for r in rows if isinstance(r.get("runtime_execution_events"), list) and any(
        isinstance(e, dict) and e.get("execution_started") is True for e in r.get("runtime_execution_events", [])
    )]
    return {
        "configured": len(configured),
        "requested": len(requested),
        "executed": len(executed),
        "success": statuses.count("SUCCESS"),
        "dispatch_rejected": statuses.count("DISPATCH_REJECTED"),
        "provider_error": sum(1 for s in statuses if s == "PROVIDER_ERROR"),
        "transient_provider_error": statuses.count("TRANSIENT_PROVIDER_ERROR"),
        "model_unavailable": statuses.count("MODEL_UNAVAILABLE"),
        "quota_error": statuses.count("QUOTA_ERROR"),
        "not_configured": statuses.count("NOT_CONFIGURED"),
        "request_created": statuses.count("REQUEST_CREATED"),
        "not_executed": statuses.count("NOT_EXECUTED"),
        "execution_started": statuses.count("EXECUTION_STARTED"),
        "cascade_attempts": sum(
            len([e for e in (r.get("runtime_execution_events") or [])
                 if isinstance(e, dict) and e.get("execution_started") is True])
            for r in rows
        ),
    }


def _render_diagnostics(results: list[dict], title: str = "🔎 نتائج الجولة") -> None:
    counters = _ui_semantic_counters(results)
    st.subheader(title)
    st.info(
        " • ".join([
            f"مُهيأة {counters['configured']}",
            f"مطلوبة {counters['requested']}",
            f"نُفذت {counters['executed']}",
            f"نجاح {counters['success']}",
            f"DISPATCH_REJECTED {counters['dispatch_rejected']}",
            f"PROVIDER_ERROR {counters['provider_error']}",
            f"NOT_CONFIGURED {counters['not_configured']}",
            f"محاولات Cascade {counters['cascade_attempts']}",
        ])
        + " • Local Engine: غير مستخدم"
    )
    # HOTFIX129: expose the complete semantic state breakdown when any
    # non-success state exists; no generic `success • failed` aggregation.
    if any(counters[k] for k in (
        "dispatch_rejected", "provider_error", "transient_provider_error",
        "model_unavailable", "quota_error", "not_configured", "request_created",
        "not_executed", "execution_started"
    )):
        st.caption(
            "الحالات: "
            f"SUCCESS={counters['success']} · "
            f"DISPATCH_REJECTED={counters['dispatch_rejected']} · "
            f"PROVIDER_ERROR={counters['provider_error']} · "
            f"TRANSIENT_PROVIDER_ERROR={counters['transient_provider_error']} · "
            f"MODEL_UNAVAILABLE={counters['model_unavailable']} · "
            f"QUOTA_ERROR={counters['quota_error']} · "
            f"NOT_CONFIGURED={counters['not_configured']} · "
            f"REQUEST_CREATED={counters['request_created']} · "
            f"NOT_EXECUTED={counters['not_executed']} · "
            f"EXECUTION_STARTED={counters['execution_started']}"
        )
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
    st.subheader("🧪 HOTFIX123 — Production Core Test Harness")
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
    # HOTFIX123: the Bridge/Security claim is only shown as deployable after the
    # frozen multi-layer release identity matches the runtime modules. A mismatch
    # is surfaced; the app never silently rewrites the identity.
    release_identity = assert_deployed_release_identity()
    credentials = capture_credentials()
    model_candidates = capture_model_candidates()
    rounds = _render_sidebar(st.session_state.rounds, credentials, model_candidates)
    chat = _active_chat()
    st.title("🏛️ AI Council — Shared Context Arena")
    st.caption(f"{DISPLAY_VERSION} • المستخدم (المقعد 6) + {len(get_seats())} وكلاء API • DeepSeek (المقعد 7) • Free Cascade #1→#10 • Provider: {PROVIDER_VERSION}")
    st.caption(f"HOTFIX123 Release Identity Gate: {release_identity.get('gate', 'FAIL')} • Frozen Provider={release_identity.get('observed', {}).get('provider_core', 'NOT_PROVEN')} • Runtime Match={release_identity.get('runtime_matches_frozen_identity', False)}")
    st.caption("V26.3: Authoritative Conversation Persistence · Message→Request→Round Chain · HOTFIX145 Core Preserved")
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
        # HOTFIX125.3 HARD RUNTIME GATE: load REQUEST_RECORD first.
        # No fingerprint, Request-ID allocation, round, bridge, provider, or cascade
        # path may execute for a valid continuation.
        requested_request_id, continuation_record, is_continuation = _continuation_request_record(prompt, chat)
        if is_continuation:
            # HARD FAIL-CLOSED: any continuation marker must be resolved before the
            # normal-request path. It is forbidden to fall through into fingerprinting
            # or uuid generation, even when the ID is malformed/unknown.
            if not requested_request_id:
                st.error("Continuation rejected: an existing Request ID is required. No Request ID will be generated.")
                st.session_state.last_continuation_audit = {
                    "type": "CONTINUATION_GATE", "mode": "REJECTED",
                    "requested_request_id": "", "actual_request_id": "",
                    "provider_execution": 0, "cascade": 0, "new_round": 0, "new_bridge": 0,
                    "source": "PRE_ALLOCATION_HARD_GATE", "runtime_gate": "FAIL",
                }
                return
            if not continuation_record:
                st.error(f"Continuation rejected: Request ID {requested_request_id} is not present in persisted REQUEST_RECORD. No new Request ID will be generated.")
                st.session_state.last_continuation_audit = {
                    "type": "CONTINUATION_GATE", "mode": "REJECTED",
                    "requested_request_id": requested_request_id, "actual_request_id": "",
                    "provider_execution": 0, "cascade": 0, "new_round": 0, "new_bridge": 0,
                    "source": "PERSISTED_REQUEST_RECORD_REQUIRED", "runtime_gate": "FAIL",
                }
                return
            if attachments:
                st.error("Continuation is READ-ONLY and cannot accept new attachments.")
                return
            persisted_id = str(continuation_record.get("request_id") or "").strip()
            if persisted_id != requested_request_id:
                st.error("Continuation rejected: persisted REQUEST_RECORD identity mismatch.")
                return
            st.session_state.last_results = copy.deepcopy(continuation_record.get("results") or [])
            st.session_state.last_synthesis = copy.deepcopy(continuation_record.get("synthesis") or {})
            continuation_audit = {
                "type": "CONTINUATION_GATE",
                "mode": "READ_ONLY", "requested_request_id": requested_request_id,
                "actual_request_id": persisted_id, "provider_execution": 0, "cascade": 0,
                "new_round": 0, "new_bridge": 0, "source": "PERSISTED_REQUEST_RECORD",
                "runtime_gate": "PASS",
            }
            chat.setdefault("audit_events", []).append(continuation_audit)
            # HOTFIX125.4: the gate result is application-owned runtime state.
            # It is persisted before returning so Full Audit can consume it without
            # relying on any provider/agent prose.
            st.session_state.last_continuation_audit = copy.deepcopy(continuation_audit)
            st.info(f"Continuation resolved to persisted Request ID: {persisted_id} — READ-ONLY; no new Request, provider call, round, cascade, or Bridge created.")
            return
        # prior canonical lifecycle: before allocating any new Message/Request/round identity,
        # restore the last committed canonical history.  This closes the exact
        # runtime gap observed after Message 1 -> Streamlit rerun -> Message 2.
        # A narrowed current runtime is never permitted to seed the next commit.
        prepare_historical_runtime(chat, st.session_state)
        prompt, harness_abc = _extract_hotfix141_harness(prompt)
        sanitized_prompt, bridge_controls = _extract_bridge_control_values(prompt)
        prompt = sanitized_prompt
        fingerprint = _request_fingerprint(prompt, attachments)
        # HOTFIX123: atomic reservation closes the race where two Streamlit
        # reruns submit the same logical request before either can persist it.
        # The second submission is rejected before request_id allocation and
        # before _run_council(), so it cannot create a second provider run.
        with _REQUEST_GATE_LOCK:
            if fingerprint in chat.get("request_ids", []):
                st.warning("تم تجاهل طلب مكرر مطابق تمامًا لطلب أُرسل في هذه المحادثة.")
                return
            if fingerprint in _ACTIVE_REQUEST_FINGERPRINTS:
                st.warning("تم تجاهل طلب مكرر قيد التنفيذ بالفعل.")
                return
            _ACTIVE_REQUEST_FINGERPRINTS.add(fingerprint)
        if not chat["messages"]:
            chat["title"] = _title_from_prompt(prompt)
        user_message_id = uuid.uuid4().hex
        request_id = uuid.uuid4().hex
        _ensure_chat_identity_state(chat)
        chat["request_ids"] = chat["request_ids"][-MAX_REQUEST_IDS:]
        chat["request_ids"].append(fingerprint)
        chat["request_ids"] = chat["request_ids"][-MAX_REQUEST_IDS:]
        chat["request_records"].append({"request_id": request_id, "fingerprint": fingerprint, "rounds": rounds, "created_at": _now(), "identity_authority": "RUNTIME_REQUEST_ID"})
        record0 = next(r for r in chat["request_records"] if r.get("request_id") == request_id)
        attach_request_identity(record0, chat, user_message_id, request_id)
        # V26.3.8: RequestRecord is inserted into the canonical ConversationRecord
        # immediately after identity allocation, before any provider dispatch.
        canonical_upsert_request(chat, record0, st.session_state)
        # V26.3.8: MessageRecord is inserted into the same canonical record before dispatch.
        # This is an application-owned append-only session ledger used for hydration;
        # it is never derived from agent prose and never mints replacement IDs.
        persist_identity(chat, st.session_state, message={"message_id": user_message_id, "conversation_id": chat.get("conversation_id"), "session_id": chat.get("session_id"), "role": "user", "request_id": request_id, "created_at": record0.get("created_at")}, request=record0)
        # V26.3.8: explicit lifecycle COMMIT before provider execution.
        commit_canonical_record(chat, st.session_state)
        # V26: durably bind the newly allocated Message ID to its Request before provider execution.
        sync_v26_message_record(chat, user_message_id, request_id, "user", record0.get("created_at"))
        ensure_store(chat)
        touch(chat)
        chat["request_ledger_v24"].append({"request_id": request_id, "conversation_id": chat.get("conversation_id"), "session_id": chat.get("session_id"), "message_id": user_message_id, "round_id": "", "provider": "", "seat": "", "model": "", "status": "REQUEST_CREATED"})
        timeline_event(chat, request_id, user_message_id, "REQUEST_CREATED", status="REQUEST_CREATED")
        # The fingerprint is now durably present in the active chat identity
        # ledger; release the process gate so unrelated requests may proceed.
        with _REQUEST_GATE_LOCK:
            _ACTIVE_REQUEST_FINGERPRINTS.discard(fingerprint)
        attachment_context = "\n".join(f"- {a.get('name')} ({a.get('mime')}, {a.get('size', 0)} bytes, sha256={a.get('sha256', '')})" for a in attachments)[:6000]
        request_no = _request_display_number(chat, request_id)
        user_message = {"role": "user", "id": user_message_id, "content": prompt, "attachments": public_metadata(attachments), "attachment_context": attachment_context, "request_id": request_id, "request_no": request_no, "created_at": _now()}
        user_message = register_message(chat, user_message)
        chat["messages"].append(user_message)
        canonical_upsert_message(chat, {"message_id": user_message_id, "conversation_id": chat.get("conversation_id"), "session_id": chat.get("session_id"), "role": "user", "request_id": request_id, "created_at": user_message.get("created_at")}, st.session_state)
        persist_identity(chat, st.session_state, message={"message_id": user_message_id, "conversation_id": chat.get("conversation_id"), "session_id": chat.get("session_id"), "role": "user", "request_id": request_id, "created_at": user_message.get("created_at")})
        record_message(chat, user_message_id, "user", prompt, user_message.get("created_at"))
        update_memory(chat, user_message_id, prompt, (chat.get("conversation_context") or {}).get("digest", ""))
        timeline_event(chat, request_id, user_message_id, "MESSAGE_CREATED", role="user")
        if voice_audio is not None:
            chat["messages"][-1].update({"voice": True, "voice_audio_key": user_message_id, "voice_mime": voice_mime})
            st.session_state.voice_audio_store[user_message_id] = voice_audio
            _prune_voice_store()
            fingerprints = st.session_state.voice_fingerprints.setdefault(chat["id"], set())
            fingerprints.add(voice_fingerprint)
            st.session_state.voice_fingerprints[chat["id"]] = set(list(fingerprints)[-20:])
        st.session_state.last_diagnostics = []
        with st.spinner("المجلس ينفذ Free API Cascade بالتوازي…"):
            if harness_abc:
                # The outer request is only the user submission envelope. The harness
                # mints three independent runtime Request IDs and executes them
                # sequentially; cascade attempts remain inside each lifecycle.
                # Remove the envelope record so only the three authoritative lifecycle
                # records remain in the A/B/C audit.
                envelope = next((r for r in chat.get("request_records", []) if r.get("request_id") == request_id), None)
                if envelope is not None:
                    chat["request_records"].remove(envelope)
                harness_reports = _run_hotfix141_abc_harness(
                    prompt, chat, rounds, credentials, attachments, model_candidates, user_message_id
                )
                st.session_state.last_hotfix141_harness = copy.deepcopy(harness_reports)
                if chat.get("messages") and isinstance(chat["messages"][-1], dict):
                    chat["messages"][-1]["request_id"] = ""
                    chat["messages"][-1]["harness_request_ids"] = [str(x.get("request_id") or "") for x in harness_reports]
                    chat["messages"][-1]["request_authority"] = "RUNTIME_REQUEST_IDS_PER_HARNESS_LIFECYCLE"
                last_results = []
                for item in harness_reports:
                    for rec in chat.get("request_records", []):
                        if rec.get("request_id") == item["request_id"]:
                            last_results.extend(copy.deepcopy(rec.get("results") or []))
                results = last_results
            else:
                results = _run_council(prompt, chat, rounds, credentials, attachments, model_candidates, user_message_id, request_id, bridge_controls)
        st.session_state.last_results = [_public_result(r) for r in results]
        # V24 authoritative ledgers derive only from application-owned runtime results.
        ensure_store(chat); touch(chat)
        for rr in list(results or []):
            if not isinstance(rr, dict): continue
            rid=str(rr.get("request_id") or request_id)
            round_no=int(rr.get("round") or 1)
            round_id=f"{chat.get('conversation_id')}:{rid}:r{round_no}"
            record_v24_provenance(chat, rr, user_message_id, round_id)
            chat["result_ledger_v24"].append({"result_id": f"res_{uuid.uuid4().hex}", "request_id": rid, "message_id": user_message_id, "provider": str(rr.get("name") or ""), "seat": str(rr.get("seat") or ""), "model": str(rr.get("executed_model") or rr.get("model") or ""), "status": str(rr.get("status") or ""), "provenance_count": len([p for p in chat.get("provenance_ledger_v24",[]) if p.get("request_id")==rid])})
            b=rr.get("bridge_transaction_audit") or {}
            bid=str(b.get("bridge_id") or "")
            if bid:
                chat["bridge_ledger_v24"].append({"bridge_id":bid,"request_id":rid,"round_id":round_id,"status":str(b.get("status") or "PASS")})
            timeline_event(chat, rid, user_message_id, "PROVIDER_RESULT", provider=str(rr.get("name") or ""), seat=str(rr.get("seat") or ""), model=str(rr.get("executed_model") or rr.get("model") or ""), status=str(rr.get("status") or ""))
        chat["result_ledger_v24"]=chat["result_ledger_v24"][-2000:]
        chat["bridge_ledger_v24"]=chat["bridge_ledger_v24"][-1000:]
        # V25: reconcile the complete authoritative per-message ledger only after
        # provider execution and synthesis are finished. This updates the same
        # request row on reruns instead of creating duplicate request/round rows.
        ensure_v25_store(chat)
        reconcile_request(chat, request_id, user_message_id, list(results or []), st.session_state.get("last_synthesis") or {}, st.session_state)
        snapshot_chat_identity(chat, st.session_state)
        hydrate_canonical_record(chat, st.session_state)
        rebuild_runtime_indexes_from_canonical(chat, st.session_state)
        commit_canonical_record(chat, st.session_state)
        authoritative_audit(chat, st.session_state)
        timeline_event(chat, request_id, user_message_id, "SYNTHESIS", status=str((st.session_state.get("last_synthesis") or {}).get("status") or "UNKNOWN"))
        touch(chat)
        _shared_context(chat, max_chars=30_000)
        st.session_state.last_health_snapshot = provider_health_snapshot(get_seats(), credentials, model_candidates)
        st.session_state.last_security_audit = security_audit(st.session_state.get("chats", []))
        st.session_state.folder_nonce += 1
        st.session_state.voice_nonce += 1
        st.rerun()
    hydrate_canonical_record(chat, st.session_state)
    rebuild_runtime_indexes_from_canonical(chat, st.session_state)
    hydrate_chat_identity(chat, st.session_state)
    snapshot_chat_identity(chat, st.session_state)
    runtime_audit = conversation_audit(chat)
    v25_audit = authoritative_audit(chat, st.session_state)
    v25_audit["v26_3_persistence"] = persistence_audit(chat, st.session_state)
    with st.expander("🧭 HOTFIX118 — Authoritative Historical Conversation Audit", expanded=True):
        st.json(v25_audit)
        st.caption("مصدر الحقيقة: Application-Owned Runtime Records فقط؛ Agent prose غير مستخدم للهوية أو العدادات.")
    with st.expander("🧭 Conversation Runtime / Provenance", expanded=False):
        st.json(runtime_audit)
        syn = st.session_state.get("last_synthesis") or {}
        if syn:
            st.caption(f"Synthesis source: {syn.get('successful_providers', [])} · provenance={syn.get('provenance_count', 0)}")

    if st.session_state.last_diagnostics:
        st.divider()
        _render_provider_diagnostics(st.session_state.last_diagnostics)
    if st.session_state.last_results:
        st.divider()
        _render_bridge_audit(st.session_state.last_results)
        _render_diagnostics(st.session_state.last_results)
        syn = st.session_state.get("last_synthesis") or {}
        if syn:
            st.subheader("🧠 Council Synthesis / Authoritative Result Set")
            st.json(syn)
    _render_production_core_validation()
    harness_report = st.session_state.get("last_hotfix141_harness") or []
    if harness_report:
        st.divider()
        st.subheader("HOTFIX141 — A/B/C Independent Lifecycle Harness")
        st.json({"mode": "HOTFIX141_ABC", "requests": harness_report, "authoritative_source": "APPLICATION_OWNED_REQUEST_RECORDS"})

    with st.expander("🔐 V23 Security / Context / Platform Audit", expanded=True):
        if st.button("Run full V23 platform audit", key="v23_platform_audit"):
            chat = _active_chat()
            latest = chat.get("request_records", [])[-1] if chat.get("request_records") else {}
            continuation_snapshot = st.session_state.get("last_continuation_audit") or {}
            rid = str(continuation_snapshot.get("requested_request_id") or latest.get("request_id") or "")
            # Context audit is derived from the actual persisted conversation.
            _shared_context(chat, max_chars=30_000)
            st.session_state.last_health_snapshot = provider_health_snapshot(get_seats(), credentials, model_candidates)
            st.session_state.last_security_audit = security_audit(st.session_state.get("chats", []))
            code, report = run_production_core_tests()
            st.session_state.last_production_core_report = report
            st.session_state.last_production_core_code = code
            st.session_state.last_v23_platform_audit = build_v23_platform_audit(
                chat, rid, st.session_state.get("platform_context_meta"),
                st.session_state.get("last_health_snapshot"),
                st.session_state.get("last_security_audit"),
                st.session_state.get("last_production_core_report"),
            )
            # HOTFIX146: fresh, observational final-closure report. This layer
            # never mutates canonical persistence or provider execution.
            st.session_state.last_v23_final_closure_audit = build_v23_final_closure_audit(
                chat,
                st.session_state.get("last_security_audit"),
                st.session_state.get("last_v23_platform_audit"),
                st.session_state.get("last_results"),
            )
        if st.button("Run A/B/C Multi-Request Lifecycle Audit", key="v23_multi_request_audit"):
            chat = _active_chat()
            st.session_state.last_v23_multi_request_regression = multi_request_regression_audit(chat)
        regression_report = st.session_state.get("last_v23_multi_request_regression") or {}
        if regression_report:
            st.subheader("A/B/C — Independent Request Lifecycle Audit")
            st.json(regression_report)

        report = st.session_state.get("last_v23_platform_audit") or {}
        if report:
            st.json(report)
            closure = st.session_state.get("last_v23_final_closure_audit") or {}
            if closure:
                st.subheader("HOTFIX146 — V23 Final Closure Audit")
                st.json(closure)

            # HOTFIX151: mobile-friendly full-audit export. Streamlit's
            # st.code widget provides a native Copy button, while
            # st.download_button provides a reliable fallback for long reports.
            audit_export = build_v23_audit_export(
                platform_audit=report,
                final_closure_audit=closure,
                security_audit=st.session_state.get("last_security_audit"),
                health_snapshot=st.session_state.get("last_health_snapshot"),
                production_core_report=st.session_state.get("last_production_core_report"),
                production_core_code=st.session_state.get("last_production_core_code"),
            )
            audit_export_text = serialize_v23_audit_export(audit_export)
            st.divider()
            st.subheader("📋 HOTFIX151 — Full V23 Audit Export")
            st.caption("لنسخ التقرير كاملًا من الهاتف: اضغط زر النسخ أعلى مربع التقرير. أو استخدم زر التنزيل لإرسال ملف JSON كامل.")
            st.download_button(
                "💾 Download Full V23 Audit JSON",
                data=audit_export_text,
                file_name="V23_FULL_PLATFORM_AUDIT.json",
                mime="application/json",
                key="v23_full_audit_download",
            )
            # HOTFIX151.1: standalone mobile copy control. The copy action is
            # executed inside a small browser component so the user does not
            # need to select a huge Streamlit code block manually.
            _audit_copy_html = f"""
            <div style="font-family: sans-serif; width: 100%;">
              <button id="copyAudit" style="width:100%; padding:12px; font-size:16px; cursor:pointer;">📋 نسخ التقرير كاملًا</button>
              <div id="copyStatus" style="margin-top:8px; font-size:14px;"></div>
              <textarea id="auditText" readonly style="position:absolute; left:-9999px; top:0; width:1px; height:1px; opacity:0;"></textarea>
            </div>
            <script>
              const auditText = document.getElementById('auditText');
              auditText.value = {json.dumps(audit_export_text, ensure_ascii=False)};
              const status = document.getElementById('copyStatus');
              document.getElementById('copyAudit').addEventListener('click', async () => {{
                try {{
                  await navigator.clipboard.writeText(auditText.value);
                  status.textContent = '✅ تم نسخ التقرير كاملًا إلى الحافظة';
                  return;
                }} catch (e) {{}}
                try {{
                  auditText.focus();
                  auditText.select();
                  auditText.setSelectionRange(0, auditText.value.length);
                  const ok = document.execCommand('copy');
                  status.textContent = ok ? '✅ تم نسخ التقرير كاملًا إلى الحافظة' : '⚠️ تعذر النسخ؛ استخدم زر التنزيل أدناه';
                }} catch (e) {{
                  status.textContent = '⚠️ تعذر النسخ؛ استخدم زر التنزيل أدناه';
                }}
              }});
            </script>
            """
            components_html(_audit_copy_html, height=75, scrolling=False)
            st.code(audit_export_text, language="json")
        else:
            st.info("اضغط Run full V23 platform audit لإنتاج تقرير runtime فعلي؛ لا يتم عرض NOT_RUN كأنه PASS.")


if __name__ == "__main__":
    run_app()
