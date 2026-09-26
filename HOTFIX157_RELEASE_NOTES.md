# HOTFIX157 — CANONICAL IDENTITY + RUNTIME COUNTER + BRIDGE TRANSACTION CONSISTENCY CLOSURE

This hotfix is additive on top of HOTFIX156 and preserves the existing UI/mobile layer.

## Canonical Round Evidence
- Canonical audit now proves the actual persisted history window: one-message/one-request/one-round is a valid complete lifecycle.
- The two-message historical contract remains supported when two canonical user messages exist.
- Exact Message → Request → Round evidence is derived only from Application-Owned Canonical Conversation Store records.
- A missing second request remains `NOT_PROVEN`; it is never fabricated.
- `canonical_request_round_binding_proven` is true only when the actual persisted lifecycle has exact canonical identity evidence.

## Runtime Counters
- `execution_started` is counted from persisted `runtime_execution_events` where `execution_started=true`, not from a synthetic result-status label.
- Successful provider results are canonicalized as `classification=SUCCESS` when the actual provider execution returned success.
- Existing Free Cascade attempt telemetry remains unchanged.

## Bridge / Identity Safety
- Existing transactional Bridge behavior is preserved.
- Canonical lifecycle gating remains fail-closed before provider dispatch.
- No provider credentials, raw payloads, agent prose, Local Engine, or Paid fallback are introduced.

## Regression
- Full regression suite: 541 passed.
- Baseline source was HOTFIX156 corrected package; no baseline files were removed.
