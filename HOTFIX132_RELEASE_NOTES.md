# HOTFIX132 — DISPATCH GATE / PROVIDER EXECUTION CONTRACT RECONCILIATION

## Root cause fixed
The pre-execution provider-boundary check incorrectly concatenated the user diagnostic prompt with the provider prompt. A diagnostic prompt containing the literal `BRIDGE_RESULT` therefore triggered the no-leak guard before any provider call, producing `DISPATCH_REJECTED` for configured providers and zero execution events.

## Fix
- Validate bridge non-leak only against the actual sanitized provider-layer prompt.
- Add an authoritative HOTFIX132 dispatch gate for request identity, round, credential, and explicit Free model candidates.
- `DISPATCH_ACCEPTED` is recorded before entering the Provider Execution Contract.
- Exceptions after dispatch acceptance are classified as execution/provider errors, never as dispatch rejection.
- Preserve Free #1→#10, official API only, no Local Engine, no Paid fallback, no automatic model selection.
- Preserve Request Lifecycle, single-request determinism, Transactional Bridge, runtime accounting, authoritative counters, and HOTFIX132 prose isolation.
- No credentials or bridge values are persisted in UI/history/logs.

## Scope
This hotfix changes the dispatch boundary only. Secrets, explicit `*_FREE_MODELS`, provider adapters, and cascade ordering are not changed.
