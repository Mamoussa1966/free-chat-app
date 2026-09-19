# HOTFIX125.3 — CONTINUATION RUNTIME GATE + BRIDGE ISOLATION HARDENING

Limited patch on top of HOTFIX125.1.

## Runtime fixes
- Canonical Request ID: continuation can only reuse a Request ID found in persisted `REQUEST_RECORD`; unknown continuation IDs are rejected before allocation, so no regeneration occurs.
- Continuation is READ-ONLY: zero provider executions, zero cascade attempts, zero new rounds, zero new bridges.
- Bridge control plane: user-supplied bridge control records are removed from the persisted/user/provider prompt path and stored only in application-owned bridge state.
- Bridge state is persisted on the authoritative request record and is used for application-owned audit reconstruction.
- Bridge transaction proof is evaluated from persisted application state and runtime audit fields, never agent prose.
- `Run full V23 platform audit` now executes the production test harness every time the button is pressed; it does not reuse an old PASS report.
- V23 audit explicitly gates bridge isolation when the runtime audit contains isolation fields.

## Preservation
- Official API only; no Local Engine; no Paid fallback; no automatic model selection.
- No Secrets or `*_FREE_MODELS` changes.
- Existing files are preserved; no baseline files are deleted.
- HOTFIX123.2 request/cascade identity behavior remains regression-tested.


## HOTFIX125.3 hard gates
- Continuation resolves the persisted REQUEST_RECORD before fingerprinting or Request-ID allocation.
- Valid continuation is read-only; provider execution, cascade attempts, round creation, and bridge creation are hard-rejected.
- Bridge audit is sourced from persisted application-owned state and runtime payload attestations, never agent prose.
- BRIDGE_RESULT and its control value are removed before provider-layer construction; boundary assertions fail closed.
- Runtime platform audit cannot PASS when requested Request ID differs from the actual persisted Request ID.
- Full V23 audit invokes the real Production Core test harness; harness PASS is never inferred from agent text.
- No Secrets or model lists changed; no baseline files deleted.

## Preservation of HOTFIX125.1 contract
- REQUEST CONTINUATION + BRIDGE ISOLATION REGRESSION FIX behavior remains covered by the existing regression suite.
