# HOTFIX125 — CONVERSATION PERSISTENCE + V23 AUDIT CONTINUATION

Base: V23.0 HOTFIX124→HOTFIX130 Release Candidate / HOTFIX123.2 core.

Scope is additive and preserves the existing provider, Secret, model-list, cascade, Request ID, and Transactional Bridge contracts.

## Changes
- Adds application-owned Conversation Persistence audit for Session identity, User message, Request ID, Round ID, seat results, executed-model records, cascade summaries, Bridge audit, synthesis, and authoritative request metrics.
- Explicitly detects forbidden persisted data: API keys, authorization headers, raw provider payloads, and sensitive attempt diagnostics.
- Adds Session Integrity audit for duplicate Request IDs, duplicate Seat+Round ledger entries, and duplicate Bridge IDs.
- Produces a single V23 platform audit object covering Security, Context Window, Conversation Persistence, Session Integrity, Provider Health, and Regression Core.
- Executes context audit from the actual persisted conversation after a completed request instead of leaving Context metadata empty.
- Runs the local Production Core test harness when the full V23 audit is requested and no current report exists.
- UI no longer presents `NOT_RUN` as the audit result after a completed request; it provides an explicit action to generate the runtime audit and renders the resulting application-owned report.

## Preserved contracts
- Official API only.
- No Local Engine.
- No Paid fallback.
- No Dynamic Model Discovery.
- Existing `*_FREE_MODELS` unchanged.
- Existing Streamlit Secrets/model configuration unchanged.
- Request ID remains application/lifecycle authoritative.
- Agent-generated prose is never used as an audit counter source.
- Existing files are preserved; this package is additive over the V23 Release Candidate baseline.

## Verification
Full pytest suite: 349 passed.
Focused HOTFIX125/V23 tests: 7 passed.
