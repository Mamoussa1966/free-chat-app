# HOTFIX129 — RESULT COUNTER / UI SEMANTIC CONSISTENCY

Built directly from the complete HOTFIX128 artifact. No existing files are removed.

## Scope — UI presentation only
- Replaces the generic `successful • failed` summary with state-specific counters.
- Separates CONFIGURED, REQUESTED, EXECUTED, SUCCESS, DISPATCH_REJECTED, PROVIDER_ERROR, NOT_CONFIGURED and CASCADE_ATTEMPTS in the visible result summary.
- Also exposes TRANSIENT_PROVIDER_ERROR, MODEL_UNAVAILABLE, QUOTA_ERROR, REQUEST_CREATED, NOT_EXECUTED and EXECUTION_STARTED when present.
- `DISPATCH_REJECTED` is never counted as a provider failure.
- `NOT_CONFIGURED` is never counted as a provider failure.
- Runtime execution events remain the only source for the UI's EXECUTED/CASCADE_ATTEMPTS presentation projection.

## Explicitly unchanged
- Authoritative runtime accounting / request metrics.
- Request ID lifecycle and single-request determinism.
- Free Cascade controller and live cascade telemetry.
- Provider Execution Contract.
- Transactional Bridge and prompt non-leak behavior.
- Secrets, `*_FREE_MODELS`, provider credentials, provider endpoints and model lists.
- No Local Engine and no Paid fallback.

## Regression coverage
- Added `tests/test_hotfix129_result_counter_ui.py`.
- Focused regression: 2 tests passing.
