# HOTFIX63 — strict per-cascade-attempt latency

V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX63-FINAL

- Built directly from HOTFIX63 and preserves the complete current project tree and all existing test modules.
- Enforces a hard 2.0-second HTTP timeout budget for every individual cascade-model attempt across all official API adapters.
- Hidden HTTP retries remain disabled in provider adapters; cascade failover remains the only model-level retry mechanism.
- Attempt telemetry now records latency and timeout for every provider, not Gemini only.
- Reduces the default output-token budget to 512 to improve the probability of completing useful short answers within the 2-second attempt budget; it remains configurable via `MAX_OUTPUT_TOKENS`.
- Preserves room seats: ChatGPT 1, Gemini 2, Claude 3, Grok 4, Kimi 5, human user 6, DeepSeek 7, configured extra agents 8–20.
- Preserves explicit `DEEPSEEK_FREE_MODELS` only; no automatic model, paid fallback, or Local Engine.

# HOTFIX63 — 2-second cascade attempt hardening

V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX63-FINAL

- Built directly from HOTFIX63 while preserving the complete project tree and all existing test modules.
- Enforces a hard 2.0-second timeout for every individual cascade-model HTTP attempt across all official adapters and dynamic seats.
- Disables hidden HTTP retries from extending an individual attempt beyond the 2-second contract.
- Keeps the explicit Free-model cascade as the only model failover mechanism.
- Keeps user seat 6 reserved for the human operator, DeepSeek at seat 7, and dynamic seats 8–20.
- Adds regression coverage for the uniform 2-second attempt contract.

# HOTFIX63 — DeepSeek execution/identity hardening

V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX63-FINAL

- Preserves the current six official API agents plus the human operator as room seat 6; DeepSeek remains room seat 7 and configured extras start at seat 8.
- Preserves every existing `tests/test_*.py` module and the current dynamic test-set invariant.
- DeepSeek continues to use only explicit `DEEPSEEK_API_KEY` and `DEEPSEEK_FREE_MODELS` configuration; no implicit free model is introduced.
- DeepSeek V4 provider identity attestation now accepts the documented deployed-version aliases for a requested stable model ID (for example `deepseek-v4-flash` ↔ `deepseek-v4-flash-0731`) while rejecting unrelated identities.
- Failure rendering no longer falls back to `UNKNOWN` merely because a result has no raw error payload; it derives the stable public classification from the sanitized result metadata.
- No Local Engine, no paid fallback, and no credential values are packaged or rendered.

V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX63-FINAL

# HOTFIX63 — Gemini latency hardening

V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX63-FINAL

# previous multi-agent release MULTIAGENT FINAL

## DeepSeek configuration discovery hardening

- Strengthens Streamlit Secrets resolution for `DEEPSEEK_API_KEY` and `DEEPSEEK_FREE_MODELS`.
- Canonical key matching is case-insensitive and strips UTF-8 BOM / zero-width characters from secret key names.
- Exact canonical keys are recursively resolved through nested TOML tables without cross-binding unrelated provider credentials.
- Streamlit Secrets remain authoritative over environment variables.
- No implicit DeepSeek model catalog is introduced.
- Official DeepSeek endpoint and provider-model identity attestation remain unchanged.

Version: `V22.1-FINAL-EXACT-NAMES-UPDATED-previous multi-agent release-FINAL`

# previous release-FINAL

## DeepSeek credential/configuration and multi-agent execution hardening

- DeepSeek remains a first-class sixth agent with its own explicit `DEEPSEEK_API_KEY` and `DEEPSEEK_FREE_MODELS` path.
- Streamlit Secret resolution is hardened across root keys, case variants, nested provider tables, Streamlit secret objects, and TOML-array model values, while preserving Secret-over-environment precedence.
- DeepSeek uses the official `https://api.deepseek.com/chat/completions` OpenAI-compatible endpoint and sends a text `messages[].content` payload.
- Successful DeepSeek requests require provider-attested `response["model"]`; identity mismatch or missing provider identity fails closed.
- The council execution and diagnostic paths now use the dynamic seat registry, so configured extra agents can execute instead of being rendered only.
- The room supports up to 20 total agents: six canonical agents plus up to fourteen explicitly configured additional agents.
- No implicit model discovery, no paid fallback, and no local engine were added.

## previous release — DeepSeek Secret Resolver Hardening

- Hardened Streamlit Secrets discovery for `DEEPSEEK_API_KEY` and `DEEPSEEK_FREE_MODELS`.
- Added direct, case-insensitive canonical lookup plus provider-scoped TOML table support.
- Preserved strict provider isolation: unrelated generic `api_key` values cannot cross-bind to DeepSeek.
- Preserved explicit model-candidate policy; no implicit Free model is introduced.
- Preserved DeepSeek provider model attestation: request model must equal provider response `model`, then `executed_model` and UI model.
- Added regression tests for Streamlit-like Secret containers and cross-provider isolation.

## previous release — DeepSeek Secrets resolver hardening

- Reworked Streamlit Secrets resolution to support both the native mapping and `st.secrets.to_dict()` representations.
- Provider-scoped nested tables such as `[deepseek]` and `[providers.deepseek]` are supported without accepting generic `api_key` values from unrelated provider tables.
- Canonical nested `DEEPSEEK_API_KEY` / `DEEPSEEK_FREE_MODELS` keys remain supported.
- Preserved Streamlit Secrets precedence over environment variables and the explicit `DEEPSEEK_FREE_MODELS` allow-list contract.
- No Local Engine, no implicit model selection, and no paid fallback were introduced.

Version: `previous-release`

## previous release — DeepSeek Secrets discovery + provider identity hardening

- Fixed the DeepSeek credential discovery boundary so `DEEPSEEK_API_KEY` is read from Streamlit Secrets before the environment.
- Added robust root-key, case-insensitive, and nested-TOML Secret lookup without exposing credential values.
- Added non-secret credential-source diagnostics so the UI can distinguish `streamlit_secrets`, `environment`, and `missing`.
- Preserved explicit `DEEPSEEK_FREE_MODELS` only; no implicit DeepSeek model catalog is introduced.
- Preserved the official endpoint `https://api.deepseek.com/chat/completions`.
- Enforced provider-attested model identity for every official seat in the UI path: provider-reported model must exist and equal the executed model.
- Provider identity mismatch is terminal for that cascade attempt and can never be rendered as a successful round.
- Raw provider payloads and credentials remain excluded from visible History.

Version: `previous-release`

## previous release — DeepSeek Secrets discovery + provider identity hardening

Previous release — Multi-agent architecture
- Preserves the original six first-class provider agents.
- Removes the architectural assumption that the council is limited to five/six agents.
- Supports up to 20 total seats, with up to 14 explicitly configured additional agents.
- Additional agents use the same shared candidate/cascade execution path rather than provider-specific room logic.
- Existing Gemini/Claude/Grok/DeepSeek adapters remain isolated and unchanged in their provider-specific HTTP contracts.
- Added regression coverage for ordering, 20-agent cap, explicit credential/model references, and invalid configuration rejection.

# AI Council — Free Cascade

previous-release.

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

## DeepSeek integration — verification status
- Adds an official DeepSeek adapter using `https://api.deepseek.com/chat/completions`.
- Uses only explicitly configured `DEEPSEEK_FREE_MODELS`; no automatic model selection and no inferred Free entitlement.
- The current official DeepSeek API documents `deepseek-v4-flash`, `deepseek-v4-pro`, and `deepseek-v4-flash-vision-exp` as API model IDs; the official pricing page lists V4 Flash/Pro as paid API models. This project therefore does **not** infer or invent a Free entitlement.
- `DEEPSEEK_FREE_MODELS` remains an explicit allow-list by contract; a configured ID is not proof that the official DeepSeek API grants Free usage.
- DeepSeek is **VERIFIED-ADAPTER / NOT-GOLDEN** until a real official API request with a valid credential succeeds and the release gate is rerun after that live test.


## Multi-agent architecture
- The six original first-class agents remain unchanged: ChatGPT, Gemini, Claude, Grok, Kimi, and DeepSeek.
- The room is no longer structurally limited to five or six seats. Up to 20 total agents are supported.
- Additional agents are declared explicitly in `AI_COUNCIL_EXTRA_AGENTS` as JSON configuration; credentials are referenced by Secret/environment variable names and never embedded in the agent configuration.
- Additional agents reuse the same parse → normalize → candidates → call_seat → cascade contract. Supported adapter kinds are `chat_completions`, `openai_responses`, `xai_responses`, `deepseek_chat`, `gemini`, and `anthropic`.
- No Local Engine, implicit provider, automatic model selection, or paid fallback is introduced.

## Historical provider-identity hardening
- DeepSeek now requires the official response `model` field.
- The requested model, HTTP request model, provider-reported model, executed model, and displayed model must agree for a successful DeepSeek round.
- Missing or mismatched provider model identity fails closed and never renders as a successful DeepSeek response.
- Raw provider payloads remain excluded from UI/history.

## previous multi-agent release
1. Removed the last stale `SEATS` dependency from `main.py`; history lookup now uses the same dynamic seat registry as execution and diagnostics.
2. Added an integration regression covering an extra configured seat end-to-end through `_run_round`, ensuring its result is not silently discarded.
3. Kept the six original seats unchanged and retained the 20-seat cap.

# PREVIOUS_RELEASE FINAL — Dynamic 20-seat registry hardening

- The runtime now snapshots `get_seats()` once per round, diagnostic pass, and sidebar render.
- No execution, aggregation, diagnostics, credential display, or model display path uses the legacy fixed `SEATS` alias.
- Added regression coverage for dynamic extra-agent diagnostics and end-to-end round aggregation.
- The six original first-class agents remain unchanged; up to 14 configured extra agents remain supported (20 total).
- No Local Engine and no paid fallback were introduced.


## PREVIOUS_RELEASE — Dynamic Agent Registry Integrity

- The six built-in agents remain first-class: ChatGPT, Gemini, Claude, Grok, Kimi, DeepSeek.
- All main runtime surfaces resolve `get_seats()` dynamically; the compatibility alias `SEATS` is not used by `main.py`.
- Added a real round-aggregation regression proving an extra configured agent survives execution and appears in `chat["messages"]`.
- Added diagnostic aggregation coverage for extra agents.
- Removed the brittle fixed test-module count; the release gate now validates the exact declared test-file set.
- Release packaging continues to re-extract the exact ZIP and rerun the complete suite before acceptance.


## V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX63-FINAL

- Preserved the complete current project tree and all existing `tests/test_*.py` modules; the release test registry is now dynamic rather than hard-coded to an older test count.
- Added the canonical `.streamlit/secrets.toml.example` path while retaining the user's existing files.
- Hardened model parsing: ASCII separators are accepted; typographic punctuation is rejected instead of silently rewriting model IDs.
- Preserved sequential Free-model cascade execution and compatibility with test doubles that omit the optional deadline parameter.
- Preserved execution/provider identity checks and strengthened UI execution-model display.
- Council aggregation now deduplicates duplicate worker results at the orchestration boundary without weakening the low-level history-identity invariant.
- Internal worker failures are normalized to `API_ERROR` rather than an opaque `UNKNOWN`.

## HOTFIX63 Gemini latency hardening
- Built directly from the previous release codebase; existing application files and test modules are preserved.
- Gemini per-model request timeout is capped at 10 seconds by default and is configurable with `GEMINI_REQUEST_TIMEOUT_SECONDS` (5–30).
- Gemini HTTP-level retries are disabled by default because the explicit Free-model cascade already provides failover; this removes hidden retry latency.
- Every cascade attempt records latency and effective timeout for operational diagnostics.
- Successful Gemini results expose total request latency plus successful-attempt latency; raw provider payloads remain excluded from UI/history.
- Model identity attestation and the Free API Cascade contract remain unchanged.


# HOTFIX63 — ROOM SEAT / DEEPSEEK FINAL

- Corrected the room architecture: the human operator is reserved as seat 6 and is not an API provider seat.
- DeepSeek is explicitly seat 7, not seat 6.
- Dynamic agents begin at seat 8.
- Preserved the six official API adapters and the existing test files.
- Added a regression test preventing any provider from occupying room seat 6.
- Preserved the explicit `DEEPSEEK_API_KEY` → `DEEPSEEK_FREE_MODELS` contract and official `https://api.deepseek.com/chat/completions` path.


# HOTFIX63

1. Preserves the six-agent API registry plus user seat 6 and DeepSeek seat 7.
2. Keeps the existing 36 test modules; no existing test file is removed or replaced.
3. Makes final failure classification a first-class UI-safe field instead of relying only on transient diagnostics.
4. Tightens Gemini latency by reducing the default per-attempt timeout from 5s to 4s while retaining explicit cascade failover.
5. Makes the DeepSeek Chat Completions payload explicit with `stream: false` and preserves provider model identity attestation.
6. Release packaging continues to derive the exact test-file set dynamically and round-trips the ZIP before acceptance.
