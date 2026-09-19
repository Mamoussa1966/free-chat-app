# HOTFIX125.2 — REQUEST CONTINUATION + BRIDGE ISOLATION REGRESSION FIX

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
