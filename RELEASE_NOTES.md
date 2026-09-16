V22.1-HOTFIX87-PRODUCTION-HARDENED

# HOTFIX87 — Structured Bridge Write Final

## Scope
- Built directly from HOTFIX87.
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

## HOTFIX87 Production Hardening Patch — Bridge Diagnostics & Isolation

- Provider attempt telemetry is now retained in a safe UI/history envelope with: attempt, model, HTTP status, classification, retryable, execution latency, request ID, round, and final result.
- Claude and Grok failures surface their concrete HTTP status/classification when available instead of only `Official API failed`.
- Provider output is schema-validated before it is promoted into Shared Context.
- Invalid provider envelopes are rejected from the bridge and the originating provider is isolated; subsequent providers continue independently.
- No API keys, raw request payloads, or raw provider error payloads are persisted to UI/history.
- Free Cascade remains explicit `#1 → #10`; no Local Engine, no Paid fallback, and no implicit model selection.
- Added regression tests for telemetry completeness, bridge schema rejection, and provider-failure isolation.
- Release contains the complete HOTFIX87 project tree; no existing project files were removed.
