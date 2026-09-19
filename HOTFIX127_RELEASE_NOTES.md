# HOTFIX127 — EXECUTION ACCOUNTING / ATTEMPT-RECORD INTEGRITY

Base: HOTFIX126 V23 continuation-runtime hardened release.

## Fixed
1. CONFIGURED is separate from REQUESTED.
2. REQUESTED is separate from EXECUTED.
3. EXECUTED is derived only from runtime execution events.
4. SUCCESSFUL is derived only from runtime-executed successful results with content.
5. TOTAL_CASCADE_ATTEMPTS counts only actual provider attempt records.
6. Worker-level/orchestration failures do not create synthetic Attempt #1 records.
7. PROVIDER_RESULT audit events are emitted only for runtime execution events and carry attempt identity.
8. Existing request/bridge identity, Free Cascade, provider isolation, secrets isolation, and V23 layers are preserved.

## Regression invariant
`configured_seats != requested_seats != executed_seats != successful_seats` are independently calculated quantities.

No file from HOTFIX126 is intentionally deleted.
