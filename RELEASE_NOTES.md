# HOTFIX33-GROK-PARITY

Version: `V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX33-FINAL`

## Scope
1. Adds Grok/xAI as a first-class provider using the same shared architecture and operational contract already used by Gemini and Claude.
2. Uses `GROK_FREE_MODELS` as the preferred explicit model list, with `XAI_FREE_MODELS` retained as a backward-compatible alias; maximum 10 candidates.
3. Uses the official xAI Responses API at `https://api.x.ai/v1/responses` with `Authorization: Bearer <XAI_API_KEY>`.
4. Preserves the stable taxonomy: `MODEL_UNAVAILABLE`, `QUOTA_EXCEEDED`, `RATE_LIMITED`, `AUTHENTICATION_ERROR`, `API_ERROR`, `NETWORK_ERROR`, `TIMEOUT`, `UNKNOWN`.
5. Authentication failures are terminal; model-unavailable failures advance the explicit cascade; transient 429 rate limits use the shared retry/cascade policy; explicit credit/quota exhaustion is classified as `QUOTA_EXCEEDED`.
6. xAI's documented HTTP 400 incorrect-API-key case is normalized to `AUTHENTICATION_ERROR`, preventing an invalid credential from silently cascading into other models.
7. Raw xAI payloads remain transient/internal; live diagnostics and History use compact attempt summaries only.
8. Gemini and Claude behavior is not changed by this hotfix.
9. No dynamic Grok model discovery, Local Engine, automatic model selection, or paid fallback is introduced.

## Important Free-API boundary
xAI's current API documentation publishes per-token pricing for its API models and documents API rate-limit tiers. Therefore this release deliberately does **not** label any xAI model as free by default. A model is eligible for the project's Free API cascade only when the user explicitly places it in `GROK_FREE_MODELS`/`XAI_FREE_MODELS` based on the access/plan available to their account.

## Regression coverage
- Added `tests/test_grok_integration.py` covering explicit configuration precedence, no discovery, 400/401 authentication stop, model-unavailable advancement, 429 retry/cascade behavior, quota classification, exact execution identity, live diagnostic privacy, and History privacy.
- Preserved all 20 Golden baseline test modules plus the existing Claude regression module.

# HOTFIX33-CLAUDE-ATTEMPT-DIAGNOSTICS

Version: `V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX33-FINAL`

## Fix
1. Claude live failure results now expose a compact `attempt_summaries` structure directly to the diagnostic UI, so every real attempted model reports its HTTP status and stable classification without exposing the raw Anthropic payload.
2. Raw `attempt_diagnostics` and provider error text remain transient/internal; visible History continues to store only compact summaries.
3. Authentication errors remain terminal; `MODEL_UNAVAILABLE` advances the explicit Free cascade; `QUOTA_EXCEEDED` and `RATE_LIMITED` remain governed by the shared cascade policy.
4. Added a regression test proving that the live Claude failure result contains only model/status/classification/retryability metadata and never the raw provider payload.

---

# HOTFIX33-CLAUDE-HTTP-DIAGNOSTICS

Version: `V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX33-FINAL`

## Fixes
1. Claude keeps the Gemini-equivalent explicit Free cascade path; no dynamic discovery, paid fallback, Local Engine, or automatic model selection.
2. Claude HTTP failures retain the real HTTP status and stable classification internally: MODEL_UNAVAILABLE, QUOTA_EXCEEDED, RATE_LIMITED, AUTHENTICATION_ERROR, API_ERROR, NETWORK_ERROR, TIMEOUT, UNKNOWN.
3. The Claude failure UI now exposes only a compact per-attempt classification/model/status summary. Raw Anthropic payloads remain hidden.
4. Authentication errors remain terminal; model-unavailable errors advance to the next explicit Free model; quota/rate-limit behavior remains governed by the shared cascade policy.
5. Added regression coverage for real HTTP-path classification and compact public-result rendering.

---

# HOTFIX33-CLAUDE-GEMINI-PARITY

Version: `V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX33-FINAL`

## Scope
Built from the preserved full V22.1 release candidate. All existing test modules from the prior preserved baseline remain included; no test module was deleted. `gitops_layer.py` remains outside the application hotfix scope and is unchanged.

## Fixes and release hardening
1. Preserves the complete current test-file set (20 `test_*.py` modules) and enforces the exact set during source validation and ZIP verification.
2. Keeps the corrected 429 taxonomy: explicit quota/billing exhaustion is `QUOTA_EXCEEDED`; transient throttling is `RATE_LIMITED`.
3. Stops the Free-model cascade immediately on a confirmed authentication error, using the canonical public classification.
4. Keeps raw provider diagnostics transient and stores only compact classification summaries in visible History/session-state results.
5. Visible attempt diagnostics are compact and automatically expire after 60 seconds; raw provider payloads are never rendered.
6. Release tests execute in a fresh temporary copied sandbox with credential-like inherited environment variables scrubbed.
7. The exact packaged ZIP is re-extracted into a second fresh sandbox and the complete test suite is executed again before the artifact is accepted.
8. ZIP validation rejects unsafe paths and symlink members and checks the exact preserved test-file set.

## Preserved test modules
- test_attachments.py
- test_core.py
- test_entrypoint.py
- test_gitops_layer.py
- test_hardening.py
- test_hotfix13_model_identity.py
- test_hotfix14_cascade_invariants.py
- test_hotfix14_error_classification.py
- test_hotfix14_request_history_identity.py
- test_hotfix17_fixes.py
- test_hotfix18_fixes.py
- test_hotfix19_fixes.py
- test_hotfix21_release_consistency.py
- test_hotfix21_ui_privacy.py
- test_hotfix26_release_roundtrip.py
- test_provider_runtime.py
- test_v213_hardening.py
- test_v214_voice.py
- test_v215_resilience.py
- test_v216_hardening.py

## Explicit non-scope
`gitops_layer.py` remains exploratory/educational. No GitHub Push, PAT, GitHub App, or external repository mutation is performed by this release.


## Claude Integration Scope
1. Claude now follows the same architecture/behavior contract as Gemini for model configuration and Free-model cascade execution.
2. Execution uses only the explicitly configured `CLAUDE_FREE_MODELS` / `ANTHROPIC_FREE_MODELS`; no dynamic discovery, paid fallback, local engine, or automatic model selection is used.
3. Claude-specific implementation is limited to official Anthropic API specifics: endpoint, authentication headers, request payload, and response parsing.
4. Added real HTTP-path regression tests for Claude authentication, quota/rate-limit classification, model-unavailable cascade advancement, successful execution identity, and diagnostic privacy.
5. Preserved the complete 20-module baseline test set and added Claude-specific regression coverage as the 21st test module.
