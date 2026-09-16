# AI Council — Free Cascade

V22.1-HOTFIX87-PRODUCTION-HARDENED.

Free API Cascade #1→#10. No Local Engine, no paid fallback, and no implicit model selection.

Attempt diagnostics use the stable taxonomy: MODEL_UNAVAILABLE, QUOTA_EXCEEDED, RATE_LIMITED, AUTHENTICATION_ERROR, API_ERROR, NETWORK_ERROR, TIMEOUT, UNKNOWN. Raw provider error text is operational-only; visible History stores only short classifications. Authentication errors are terminal; model/quota/rate-limit/API/network/timeout failures may continue to the next explicitly configured Free model.

## Hotfix 26 Final
- Preserves all 19 existing test modules.
- Raw provider diagnostics and raw result errors are stripped before session-state result persistence.
- Visible attempt failures remain compact and auto-expire after 60 seconds.
- Quota 429s are non-retryable; transient rate-limit 429s remain retryable.
- Release validation enforces the exact test-file set and isolated sandbox execution.
- `gitops_layer.py` remains exploratory/non-push and is unchanged.

- Release artifact is re-extracted into a fresh temporary workspace and the full suite is executed a second time before release.



## Hotfix 87 Production Hardening
- Every model invocation records Provider, Attempt, Model, HTTP status, classification, retryability, execution time, Request ID, Round, and final cascade result.
- Raw provider errors and payloads remain transient and are excluded from persisted History.
- Provider output must pass schema validation before a Bridge record is created and before the output enters Shared Context.
- Handoffs are sequential within a round so the next provider receives only validated official output.
- Provider chains are isolated: a Claude failure does not cancel Gemini, Grok, Kimi, or ChatGPT.
