# HOTFIX38 FINAL-GROK-ERROR-TAXONOMY

Version: `V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX38-FINAL`

## Scope
Grok/xAI is integrated using the same shared provider architecture and behavior contract as Gemini and Claude. Gemini and Claude behavior is unchanged.

## Fixes
1. xAI authentication payload variants such as `invalid_api_key`, `invalid_authorization`, and `authentication_error` normalize to `AUTHENTICATION_ERROR` and stop the cascade.
2. HTTP 402 and credit/balance exhaustion markers normalize to `QUOTA_EXCEEDED`.
3. The generic internal `provider_error` class normalizes to `API_ERROR`, preventing false `UNKNOWN` results when the transport failed without a more specific class.
4. Transient 429 signals remain `RATE_LIMITED`; model-not-found signals remain `MODEL_UNAVAILABLE`.
5. Raw provider payloads remain transient/internal and are never persisted to visible History; UI receives compact attempt summaries only.
6. No dynamic model discovery, Local Engine, automatic model selection, or paid fallback is introduced.

## Tests
The full preserved test set remains intact: 20 baseline test modules plus Claude and Grok regression modules. Grok regressions cover explicit model configuration, authentication stop, model-unavailable advancement, rate-limit retry, quota classification, execution identity, diagnostic privacy, realistic `invalid_api_key` payloads, HTTP 402 quota, and prevention of false `UNKNOWN`.

7. Hardened the shared cascade against unexpected adapter exceptions: they are normalized into stable classifications and recorded as compact attempt diagnostics, preventing opaque worker failures from erasing the actual attempt path.
8. Expanded xAI model/auth marker normalization for additional structured error variants.

## Hotfix 36
- Fixed Grok structured-error normalization so xAI JSON error codes cannot collapse into `UNKNOWN`.
- Added real regression coverage for model-unavailable, permission-denied/authentication, rate-limit, billing, and invalid-argument payloads.
- Preserved explicit Free cascade, compact History, raw diagnostic privacy, and five-seat architecture.


## Hotfix 37 — final classification hardening
- Canonicalizes internal/provider error labels before they reach public attempt summaries.
- Prevents internal classes such as `provider_error` from becoming a visible non-taxonomy value or an avoidable `UNKNOWN`.
- Preserves Grok authentication terminality, quota/rate-limit semantics, compact History, and the shared Gemini/Claude cascade contract.


## DeepSeek adapter phase
1. Added `DeepSeek` as a provider seat using the official OpenAI-compatible Chat Completions endpoint.
2. Candidate construction is identical to Gemini/Claude/Grok: `DEEPSEEK_FREE_MODELS` → parse/normalize → `model_candidates` → `call_seat()` → ordered cascade.
3. Stable error taxonomy and authentication-terminal cascade are inherited from the hardened provider runtime.
4. Raw provider diagnostics remain runtime-only; visible History keeps compact summaries.
5. No Local Engine, no paid fallback, and no implicit model selection.
6. Official DeepSeek documentation currently lists `deepseek-v4-flash`, `deepseek-v4-pro`, and `deepseek-v4-flash-vision-exp` as API IDs; official pricing lists V4 Flash/Pro as paid. This release therefore does not falsely mark any model as Free.
7. DeepSeek Golden status remains gated on a real official API test; mocked regression tests do not count as real-provider validation.
