# HOTFIX88 — Bridge Transaction Layer

Version: `V22.1-HOTFIX88-PRODUCTION-HARDENED`

## Scope
- Built directly from the complete HOTFIX88 release tree.
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
V22.1-HOTFIX88-PRODUCTION-HARDENED

# HOTFIX88 — Structured Bridge Write Final

## Scope
- Built directly from HOTFIX88.
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


# HOTFIX88 Production Hardened

Version: `V22.1-HOTFIX88-PRODUCTION-HARDENED`

- Preserved the complete HOTFIX88 release tree and all existing tests.
- Added provider-isolation assertions so one provider cannot consume another provider's credential or model configuration.
- Expanded safe attempt telemetry with `provider`, `attempt`, `model`, `status_code`, `classification`, `retryable`, `execution_time`, `request_id`, `round`, `final_result`, and `cascade_action`.
- Claude/Grok UI diagnostics now expose compact attempt facts instead of the generic `Official API failed` message alone.
- Added deterministic provider-output schema validation before Shared Context handoff.
- Bridge records are only created from validated successful provider outputs; malformed outputs are rejected at the bridge boundary.
- No API key, request payload, response payload, or raw provider error is persisted in visible history.
