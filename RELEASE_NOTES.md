V22.1-HOTFIX87-PRODUCTION-HARDENED

# HOTFIX87 — Production Hardened Provider Reliability + Bridge

## Phase 1 — Release identity
- Unified VERSION.txt, providers.py, README.md, RELEASE_NOTES.md, build_release.py and release tests on `V22.1-HOTFIX87-PRODUCTION-HARDENED`.
- Release artifact name is derived from the current version; stale prior_bridge_baseline/prior_release_baseline production metadata was removed.

## Phase 2 — Provider Reliability
- Preserved the explicit Free Cascade #1 → #10 per provider.
- Added structured, public-safe attempt telemetry: provider, attempt, model, HTTP status, classification, retryable, latency, request ID, round and final result.
- Credentials and raw provider payloads remain outside UI/history telemetry.

## Phase 3 — Claude/Grok diagnostics
- Existing provider adapters remain isolated.
- Failures are classified at the boundary so authentication, quota, model-unavailable, timeout and API failures are distinguishable without exposing raw payloads.

## Phase 4 — Shared Context Bridge
- Preserved the structured `BRIDGE_WRITE` protocol.
- Bridge records are validated and attributed to source seat/provider/executed model.
- Bridge data remains untrusted and cannot override identity or credentials.

## Phase 5 — Provider isolation
- A failure in one provider does not cancel the other configured provider seats.
- Each provider keeps an independent explicit Free Cascade.

## Architectural proof path
`Seat 7 → DeepSeek → Bridge Write → Shared Context → Gemini → Seat 2 → Bridge Read`
