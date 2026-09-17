# HOTFIX92 — PRODUCTION CORE / COUNCIL ORCHESTRATOR HARDENING

Version: `V22.1-HOTFIX92-PRODUCTION-HARDENED`

- Built directly from the complete HOTFIX92 ZIP baseline; no baseline file is removed.
- Adds a pure production-core contract layer around the existing official API adapters.
- Adds Request Lifecycle and Round State Machine enforcement.
- Adds Provider Execution Contract: successful results require provider-attested actual model identity.
- Adds strict explicit Free Cascade #1→#10 controller; no implicit model discovery, Local Engine, or paid fallback.
- Adds explicit timeout/retry policy objects without introducing a hidden paid/local fallback.
- Adds stable failure classification boundaries.
- Adds Shared Context state machine and Transaction Bridge Guard with commit-before-read and target isolation.
- Adds secret-safe Audit Event Schema; credential values and raw provider payloads are never stored in audit events.
- Adds automated HOTFIX92 regression tests while preserving the complete existing suite.
# HOTFIX92 — Bridge Control-Plane Handoff Hardening

Version: `V22.1-HOTFIX92-PRODUCTION-HARDENED`

## Purpose
HOTFIX92 proved the application-side read resolver, but the live provider turn showed that DeepSeek could reject the protocol as if the model itself were expected to own a transactional memory bus. HOTFIX92 separates the application-owned bridge control plane from provider memory semantics.

## Fixed path
`Provider protocol output → Schema Validation → Bridge Write → Commit → Barrier → Shared Context transaction state → Provider BRIDGE_READ request → Bridge Read → Schema Validation → Seat result`

## Provider isolation
The bridge value is still never inserted into Gemini's input prompt. Gemini receives only the non-sensitive availability manifest and the explicit application control-plane contract. The application resolves the value after Gemini emits `BRIDGE_READ: BRIDGE_RESULT`.

## Preserved
- Gemini/Claude/Grok/Kimi/DeepSeek model cascades unchanged.
- Official API only.
- No Local Engine.
- No paid fallback.
- No automatic model selection.
- Seat identities and credentials unchanged.

## Security
If DeepSeek does not emit a valid write record, the bridge does not fabricate one and Gemini remains `NOT_READY`. A bridge value can only become readable after a validated write, commit, and barrier.

---

# HOTFIX92 — Transactional Bridge Read Handoff

Version: `V22.1-HOTFIX92-PRODUCTION-HARDENED`

## Scope
- Built from the complete HOTFIX92 release tree.
- Preserves all 64 HOTFIX92 files; no baseline file is removed.
- Changes only the Bridge Transaction / Shared Context handoff layer plus its release tests/version metadata.
- Provider adapters, Free API Cascade, credentials, seat identities, Official API only, no Local Engine, and no Paid fallback remain unchanged.

## Fixed path
`Provider Output → Schema Validation → Bridge Write → Commit → Round/Handoff Barrier → Shared Context → Bridge Read → Schema Validation → Next Provider`

HOTFIX92 stopped at `BRIDGE_READ_STATUS = NOT_READY` from the application perspective because the read request was resolved after Gemini's response but the resolved bridge value was not promoted to the Gemini seat result. HOTFIX92 closes that gap without a second provider call and without placing the bridge value in Gemini's input prompt.

## Security invariant
- `BRIDGE_RESULT` is never inserted into the Gemini input prompt.
- Gemini receives only the non-sensitive availability manifest and issues `BRIDGE_READ: BRIDGE_RESULT`.
- The application resolves the committed value from transactional bridge state after the response.
- A successful single read is promoted as the canonical Gemini bridge-read result.
- If the transaction is not committed and the handoff barrier is not open, the result remains `BRIDGE_READ_STATUS = NOT_READY`; no guessing is permitted.

## Trace
The bridge records `bridge_id`, `round_id`, `source_seat`, `source_provider`, `target_seat`, `key`, `write_sequence`, `commit_status`, `read_sequence`, `schema_validation`, and `request_id`.

## Validation target
DeepSeek Seat 7 performs `WRITE → VALIDATE → COMMIT → BARRIER`; Gemini Seat 2 performs `BRIDGE_READ`; the bridge resolves the exact committed value and marks `READ = PASS` and `SCHEMA_VALIDATION = PASS`.

# HOTFIX92 — Bridge Transaction Layer

Version: `V22.1-HOTFIX92-PRODUCTION-HARDENED`

## Scope
- Built directly from the complete HOTFIX92 release tree.
- Changes are confined to the Bridge Transaction Layer.
- Provider cascades, credentials, seat identities, official-API-only policy, no-local/no-paid contract, and provider adapters are preserved.

## Transaction flow
`Provider Output → Schema Validation → Bridge Write → Commit → Round/Handoff Barrier → Shared Context → Bridge Read → Schema Validation → Next Provider`

## Internal non-sensitive trace
`bridge_id`, `round_id`, `source_seat`, `source_provider`, `target_seat`, `key`, `write_sequence`, `commit_status`, `read_sequence`, `schema_validation`, `request_id`.

## Prompt isolation
Bridge values are not embedded in the next provider prompt. The prompt contains only a non-sensitive bridge-read availability manifest. A provider requests a committed value with `BRIDGE_READ: BRIDGE_RESULT`; the application resolves the value from Shared Context after the provider response.

## Validation target
DeepSeek generates a fresh value absent from the Gemini prompt, writes it, the bridge validates and commits it, the round barrier opens, and Gemini can request the value by key.
V22.1-HOTFIX92-PRODUCTION-HARDENED

# HOTFIX92 — Structured Bridge Write Final

## Scope
- Built directly from HOTFIX92.
- Preserves seat identity, provider identity, executed-model identity, Free API Cascade, official-API-only behavior, and no-paid/no-local fallback contract.
- Changes only the SharedContextBridge write protocol.

## Bridge protocol
- Provider output may contain exactly: `BRIDGE_WRITE: BRIDGE_RESULT = value`.
- The bridge parses the explicit record at the bridge boundary and stores a canonical `BRIDGE WRITE RECORD`.
- The record is attributed to source seat, source provider, and executed model.
- Later providers receive the record through Shared Context; provider adapters are not modified.
- User-provided `BRIDGE_* = value` declarations remain separate from provider-authored bridge writes.

## Architectural proof target
Seat 7 → DeepSeek → Bridge Write → Shared Context → Gemini → Seat 2 → Bridge Read.

## Safety
Bridge values remain untrusted reference data. They cannot redefine seat/provider/model identity or credentials.


# HOTFIX92 Production Hardened

Version: `V22.1-HOTFIX92-PRODUCTION-HARDENED`

- Preserved the complete HOTFIX92 release tree and all existing tests.
- Added provider-isolation assertions so one provider cannot consume another provider's credential or model configuration.
- Expanded safe attempt telemetry with `provider`, `attempt`, `model`, `status_code`, `classification`, `retryable`, `execution_time`, `request_id`, `round`, `final_result`, and `cascade_action`.
- Claude/Grok UI diagnostics now expose compact attempt facts instead of the generic `Official API failed` message alone.
- Added deterministic provider-output schema validation before Shared Context handoff.
- Bridge records are only created from validated successful provider outputs; malformed outputs are rejected at the bridge boundary.
- No API key, request payload, response payload, or raw provider error is persisted in visible history.
