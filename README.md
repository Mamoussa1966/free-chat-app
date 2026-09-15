# AI Council — Free Cascade

V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX75-FINAL.

Free API Cascade #1→#10. No Local Engine, no paid fallback, and no implicit model selection.

Attempt diagnostics use the stable taxonomy: MODEL_UNAVAILABLE, QUOTA_EXCEEDED, RATE_LIMITED, AUTHENTICATION_ERROR, API_ERROR, NETWORK_ERROR, TIMEOUT, UNKNOWN. Raw provider error text is operational-only; visible History stores only short classifications. Authentication errors are terminal; model/quota/rate-limit/API/network/timeout failures may continue to the next explicitly configured Free model.

## Current release — hard unlimited-time seat budget + cascade contract
- Official API calls use **no artificial transport timeout** (`requests` timeout is `None`).
- No per-seat wall-clock timeout or 2-second execution budget remains.
- Hidden HTTP retries remain disabled; explicitly configured Free-model candidates remain the only failover path.
- Provider latency is therefore determined by the official API, network, and provider-side processing rather than an application-imposed 2-second cutoff.
- The user remains room seat 6; DeepSeek remains seat 7; dynamic seats start at 8; total room capacity remains 20.

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
- PREVIOUS_RELEASE hardens Streamlit Secrets discovery for DeepSeek (canonical, case-insensitive, and nested TOML lookup) while preserving Secrets-first precedence and no secret leakage.
- Uses only explicitly configured `DEEPSEEK_FREE_MODELS`; no automatic model selection and no inferred Free entitlement.
- The current official DeepSeek API documents `deepseek-v4-flash`, `deepseek-v4-pro`, and `deepseek-v4-flash-vision-exp` as API model IDs; the official pricing page lists V4 Flash/Pro as paid API models. This project therefore does **not** infer or invent a Free entitlement.
- `DEEPSEEK_FREE_MODELS` remains an explicit allow-list by contract; a configured ID is not proof that the official DeepSeek API grants Free usage.
- DeepSeek is **VERIFIED-ADAPTER / NOT-GOLDEN** until a real official API request with a valid credential succeeds and the release gate is rerun after that live test.


## Multi-agent architecture
- The six original first-class agents remain unchanged: ChatGPT, Gemini, Claude, Grok, Kimi, and DeepSeek.
- The room is no longer structurally limited to five or six seats. Up to 20 total agents are supported, and the execution/diagnostic loops use the dynamic seat registry.
- Additional agents are declared explicitly in `AI_COUNCIL_EXTRA_AGENTS` as JSON configuration; credentials are referenced by Secret/environment variable names and never embedded in the agent configuration.
- Additional agents reuse the same parse → normalize → candidates → call_seat → cascade contract. Supported adapter kinds are `chat_completions`, `openai_responses`, `xai_responses`, `deepseek_chat`, `gemini`, and `anthropic`.
- No Local Engine, implicit provider, automatic model selection, or paid fallback is introduced.

## PREVIOUS_RELEASE
- Fixed the remaining static `SEATS` lookup in `main.py`; all execution, history identity, diagnostics, and UI paths now resolve the active dynamic seat set through `get_seats()`.
- Added a true integration regression proving a configured extra agent is executed by the council round and its result is returned/displayable.
- Preserved the six original first-class seats and the 20-seat dynamic architecture.


## PREVIOUS_RELEASE dynamic seat registry
The six original provider seats remain first-class. `AI_COUNCIL_EXTRA_AGENTS` can add up to 13 more official API seats (19 API seats + human seat 6 = 20 room seats). Runtime execution, aggregation, diagnostics, history identity, and sidebar configuration all use the dynamic `get_seats()` registry.


## Gemini latency hardening
Official cascade-model attempts use no artificial HTTP timeout and no hidden HTTP retry. The explicit Free-model cascade remains the failover mechanism. UI telemetry reports total latency and successful-attempt latency.


## Room seat contract
- AI seats 1–5: ChatGPT, Gemini, Claude, Grok, Kimi.
- Human operator: seat 6; it is never part of the provider registry.
- DeepSeek: seat 7; official API adapter, never an implicit/free model.
- Dynamic extra agents begin at seat 8.
- `DEEPSEEK_API_KEY` and `DEEPSEEK_FREE_MODELS` are resolved from Streamlit Secrets first.
- No API key value is rendered or persisted to chat history.

## Latency and failure observability
- Provider seats have no application-imposed wall-clock budget. The explicit Free cascade remains the only model failover mechanism.
- Every failed seat now carries a stable public `classification`, so the UI does not degrade a real authentication/quota/network/timeout failure to `UNKNOWN`.
- DeepSeek uses the official OpenAI-compatible `/chat/completions` contract with `stream: false`, explicit thinking mode, configured model identity attestation, and current documented V4 model IDs.


## No-timeout public presentation
- Built from the current no-response baseline.
- Internal transport TIMEOUT remains available to control cascade execution.
- Public/session-state results convert a pure timeout outcome to `NO_RESPONSE` status/classification.
- Pure timeout outcomes no longer render a red "Official API failed" expander or timeout attempt diagnostics.
- No model, seat, secret, cascade ordering, Local Engine, paid fallback, or automatic selection changes.
