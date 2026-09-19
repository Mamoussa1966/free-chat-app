# HOTFIX128 — RESULT STATUS SEMANTICS HARDENING

Built directly from HOTFIX127. Scope is intentionally narrow.

## Fixed
- Separates NOT_CONFIGURED, REQUEST_CREATED, DISPATCH_REJECTED, NOT_EXECUTED, EXECUTION_STARTED, PROVIDER_ERROR, TRANSIENT_PROVIDER_ERROR, MODEL_UNAVAILABLE, QUOTA_ERROR, and SUCCESS semantics.
- `attempted_models == []` can never be rendered/classified as API_ERROR or PROVIDER_ERROR.
- `Free models == 0` is NOT_CONFIGURED, never API_FAILURE.
- Zero runtime execution events cannot produce SUCCESS or prove PROVIDER_ERROR.
- Worker/orchestration failures are DISPATCH_REJECTED and do not create provider execution attempts.

## Explicitly unchanged
Secrets, `*_FREE_MODELS`, Gemini cascade, DeepSeek, Transactional Bridge, Request ID lifecycle, Free Cascade, and Provider Execution Contract.
