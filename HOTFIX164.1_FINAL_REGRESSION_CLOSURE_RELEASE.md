# HOTFIX164.1 — Transactional Bridge Final Regression Closure

Base: HOTFIX163 final closure bridge/canonical evidence release.

## Root-cause fixes

1. The application-owned `BRIDGE_RESULT` seed is now the single authoritative Bridge WRITE. A provider-generated `BRIDGE_WRITE`/`BRIDGE_RESULT` prose attempt cannot create a second WRITE/VALIDATE trace entry or overwrite the seed.
2. Target-side Bridge READ is now strictly post-provider: Gemini is dispatched first; after its official provider call returns, the application performs COMMIT → BARRIER → READ resolution. The value remains application-owned and is never inserted into the Gemini prompt or HTTP payload.
3. Existing `consume_read_requests()` remains idempotent and reuses the canonical post-provider read, preventing a second `read_sequence`.

## Acceptance evidence

- Full repository test suite: PASS.
- Temporary runtime regression probe: PASS; verified one authoritative WRITE sequence and post-provider READ ordering.
- VERSION.txt remains exactly `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`.
- No provider credentials or model configuration changes.
- No existing tests modified.
- Release ZIP is built with project files at ZIP root and is re-extracted before the second full pytest run.

## Scope

Only Transactional Bridge runtime ordering and duplicate-seed trace behavior are changed. V26.3 canonical Message → Request → Round persistence remains untouched.
