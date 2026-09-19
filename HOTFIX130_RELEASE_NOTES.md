# HOTFIX130 — AUTHORITATIVE RESULT COUNTER / UI STATE CONSISTENCY FIX

Version: `HOTFIX130`

Built from the complete HOTFIX129 artifact. No existing project files are removed.

## Narrow scope
- Presentation/semantic projection only; runtime accounting is unchanged.
- Visible counters use persisted `REQUEST_RECORD / LIFECYCLE_AUDIT` data only.
- `DISPATCH_REJECTED` and `NOT_CONFIGURED` remain independent states.
- `SUCCESS`, `EXECUTED`, `CASCADE_ATTEMPTS`, `CONFIGURED`, and `REQUESTED` use authoritative request metrics.
- Agent-generated prose is not a source for counters or Request ID.
- Telemetry Request ID is taken from the authoritative result/request identity.
- The generic `successful • failed` summary is removed.
- Regression guard rejects any generic `failed` counter when `DISPATCH_REJECTED > 0` or `NOT_CONFIGURED > 0`.

## Unchanged
- Secrets, credentials, and all `*_FREE_MODELS`.
- Cascade controller/classification.
- Transactional Bridge.
- Request Lifecycle and runtime execution accounting.
- Provider Execution Contract.
- No Local Engine / no Paid fallback.

## Regression
- `tests/test_hotfix130_authoritative_result_counter.py`
- Verifies required 4/4/2/2/2/0/2/2 authoritative counters and removal of the legacy generic summary.
