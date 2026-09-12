# AI Council — Free Cascade

V22.1 FINAL EXACT NAMES UPDATED HARDENED HOTFIX24-FINAL.

Free API Cascade #1→#10. No Local Engine, no paid fallback, and no implicit model selection.

Attempt diagnostics use the stable taxonomy: MODEL_UNAVAILABLE, QUOTA_EXCEEDED, RATE_LIMITED, AUTHENTICATION_ERROR, API_ERROR, NETWORK_ERROR, TIMEOUT, UNKNOWN. Raw provider error text is operational-only; visible History stores only short classifications. Authentication errors are terminal; model/quota/rate-limit/API/network/timeout failures may continue to the next explicitly configured Free model.

## Hotfix 24 Final
- Preserves all 19 existing test modules.
- Raw provider diagnostics and raw result errors are stripped before session-state result persistence.
- Visible attempt failures remain compact and auto-expire after 60 seconds.
- Quota 429s are non-retryable; transient rate-limit 429s remain retryable.
- Release validation enforces the exact test-file set and isolated sandbox execution.
- `gitops_layer.py` remains exploratory/non-push and is unchanged.
