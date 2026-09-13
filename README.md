# AI Council — Free Cascade

V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX42-FINAL.

Free API Cascade #1→#10. No Local Engine, no paid fallback, and no implicit model selection.

Attempt diagnostics use the stable taxonomy: MODEL_UNAVAILABLE, QUOTA_EXCEEDED, RATE_LIMITED, AUTHENTICATION_ERROR, API_ERROR, NETWORK_ERROR, TIMEOUT, UNKNOWN. Raw provider error text is operational-only; visible History stores only short classifications. Authentication errors are terminal; model/quota/rate-limit/API/network/timeout failures may continue to the next explicitly configured Free model.

## Hotfix 26 Final
- Preserves the complete 20-module Golden baseline test set.
- Raw provider diagnostics and raw result errors are stripped before session-state result persistence.
- Visible attempt failures remain compact and auto-expire after 60 seconds.
- Quota 429s are non-retryable; transient rate-limit 429s remain retryable.
- Release validation enforces the exact test-file set and isolated sandbox execution.
- `gitops_layer.py` remains exploratory/non-push and is unchanged.

- Release artifact is re-extracted into a fresh temporary workspace and the full suite is executed a second time before release.


## Grok Integration
- Official xAI Responses API only.
- `XAI_API_KEY` / `GROK_API_KEY` is read from Streamlit Secrets first, then environment.
- Grok uses the same explicit candidate/cascade architecture as Gemini and Claude. `GROK_FREE_MODELS` is preferred; `XAI_FREE_MODELS` remains a backward-compatible alias.
- No dynamic model discovery, Local Engine, automatic model selection, or paid fallback.
- The project does not assume any xAI API model is free by default; only explicitly configured candidates are eligible for this project's Free API contract.

## Claude Integration
- Official Anthropic Messages API only.
- `ANTHROPIC_API_KEY` is read from Streamlit Secrets first, then environment.
- Claude uses the same explicit Free-model configuration architecture and cascade behavior as Gemini; no dynamic model discovery path is used.
- Claude-specific behavior is limited to Anthropic API specifics (endpoint, headers, payload, and response parsing).
- Execution uses only the explicit `CLAUDE_FREE_MODELS` / `ANTHROPIC_FREE_MODELS` cascade. No paid fallback, Local Engine, or automatic model selection.

- Unexpected adapter exceptions are normalized into the stable error taxonomy instead of escaping the worker and producing an opaque UNKNOWN result with no attempt diagnostics.

## Hotfix 36
- Hardened xAI/Grok structured error classification using `error.code`, `error.type`, and message fields.
- xAI documented 403 permission failures are terminal `AUTHENTICATION_ERROR`.
- Structured model-not-found, rate-limit, billing, and invalid-argument payloads map to the stable taxonomy instead of `UNKNOWN`.
- No raw provider payload is exposed in UI or History.


## Hotfix 37 — final classification hardening
- Canonicalizes internal/provider error labels before they reach public attempt summaries.
- Prevents internal classes such as `provider_error` from becoming a visible non-taxonomy value or an avoidable `UNKNOWN`.
- Preserves Grok authentication terminality, quota/rate-limit semantics, compact History, and the shared Gemini/Claude cascade contract.

## DeepSeek integration
- Adds an official DeepSeek adapter using `https://api.deepseek.com/chat/completions`.
- Uses only explicitly configured `DEEPSEEK_FREE_MODELS`; no automatic model selection and no inferred Free entitlement.
- The current official DeepSeek API documents `deepseek-v4-flash` and `deepseek-v4-pro` as API model IDs; the official pricing page lists them as paid API models. Therefore this release does **not** label those IDs as Free by default. `deepseek-*-free` aliases are not accepted as an official DeepSeek Free catalog unless the provider itself documents them.
- DeepSeek is not Golden until a real credential/entitlement produces a successful official API test and the full release gate passes.

## HOTFIX42 — DeepSeek Secret wiring
- `DEEPSEEK_API_KEY` is read directly from the live Streamlit Secrets mapping on every app rerun, with environment fallback only when the Secret is absent/empty.
- `DEEPSEEK_FREE_MODELS` is read through the same Secrets-first configuration path; no implicit catalog is introduced.
- Credential-source diagnostics expose only `streamlit_secrets`, `environment`, or `missing` — never the credential itself.
