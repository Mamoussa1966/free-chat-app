# AI Council — Free Cascade

V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE

HOTFIX123 adds an application-owned Production Chat Reliability layer + Production Core Test Runner. Use **🧪 Run Production Core Tests** in the sidebar; the application executes the local Test Harness and renders the real PASS/NO-GO result. AI providers are not asked to run pytest.

## Current zero-cost production policy

No Local Engine, no paid fallback, and no implicit model selection. A setting named `*_FREE_MODELS` is only a model-list configuration; it is **not** proof that the vendor's API is free.

- Gemini is eligible only after the operator explicitly sets `GEMINI_API_ZERO_COST_CONFIRMED=true` after verifying the Google AI Studio project is on the Free Tier and is not attached to paid billing. Until then, **all Gemini text and voice requests are blocked before network dispatch**. The approved Gemini model IDs are `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`, and `gemini-3.1-flash-lite`.
- An optional **Cloudflare Workers AI** agent can be configured as dynamic seat 8. It requires `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_WORKERS_AI_FREE_MODELS`, an explicit `AI_COUNCIL_EXTRA_AGENTS` entry with key `cloudflare_workers_ai` and kind `cloudflare_workers_ai`, and `CLOUDFLARE_WORKERS_FREE_PLAN_CONFIRMED=true` only after the operator verifies that the account is on Workers Free. The only allowlisted Cloudflare model in this adapter is `@cf/zai-org/glm-4.7-flash`; the adapter pins the endpoint to Cloudflare's official OpenAI-compatible Workers AI endpoint and ignores user-supplied endpoint URLs for this reserved identity.
- Workers Free includes 10,000 Neurons per day shared across Workers AI models and resets at 00:00 UTC. Cloudflare states that Free-plan operations fail after the free allocation is exceeded; a Workers Paid account instead incurs charges beyond the included allocation. The confirmation flag is an operator attestation, **not a live billing-state API**. If the account is or becomes Workers Paid, unset the confirmation immediately; never upgrade the account or buy AI Gateway credits for this project. Only one Cloudflare model is enabled, so there is no secondary model attempt when a rate/usage/capacity limit is reached.
- Cloudflare documents `@cf/zai-org/glm-4.7-flash` among models available on Workers Free. Models Cloudflare explicitly marks as requiring a paid billing method are excluded, including `glm-5.2`, `glm-5.3`, `glm-5.3-flash`, Kimi K2.6/K2.7-code, and the named DeepSeek V4 models.
- The OpenAI-compatible endpoint is used directly; AI Gateway, prepaid credits, batch, and other stateful storage features are not enabled. Standard Workers AI inference has a zero-data-retention commitment and Cloudflare says it does not use Customer Content to train models; operational metadata is still retained and storage/logging features can create retention exceptions. Review the third-party model license before use.
- The current xAI Grok seat is not GroqCloud. Groq remains blocked because the public official material available to this project does not sufficiently prove the exact Free-plan over-quota billing behavior for this account. OpenAI, Claude, xAI Grok, Kimi, DeepSeek, and all other dynamic agents remain blocked from production API dispatch by default.

The operator confirmations are fail-closed safety switches, not proof obtained from a provider billing API. A `*_FREE_MODELS` string, promotional credits, a free chat-app subscription, playground access, or a trial does not prove that API use is free. Never enable a provider when its exact account tier or over-quota behavior is unclear.

The inherited Production Core layer adds a real round-scoped Shared Context Bridge. Each successful provider response is appended as untrusted reference data before the next provider call. Trusted seat/provider/executed-model identity remains authoritative and cannot be overridden by bridge content.

DeepSeek is first in bridge execution order to allow a direct DeepSeek 7 → Gemini 2 bridge test within one round. The displayed result order remains the canonical room-seat order.


The inherited bridge correction: explicit `BRIDGE_* = value` declarations in the current request are promoted into the round-scoped bridge as untrusted test data before the first provider call. Provider outputs can also emit an explicit `BRIDGE_WRITE: BRIDGE_* = value` line, which is appended to the bridge with source-seat attribution. Trusted seat/provider/model identity remains separate and authoritative. Do not use BRIDGE_* declarations for API keys or real secrets.


## Structured Bridge Write
The SharedContextBridge now normalizes explicit provider bridge writes into canonical attributed records. The intended proof path is Seat 7 → DeepSeek → Bridge Write → Shared Context → Gemini → Seat 2 → Bridge Read. This change does not modify provider adapters or the seat/identity/Free Cascade contract.


## Production Hardening
- Provider-isolated Free Cascade: each API seat owns its credential/model chain; a failure in one provider does not invoke another provider's credentials or models.
- Safe attempt telemetry includes provider, attempt, model, HTTP status, stable error classification, retryability, execution time, request ID, round, and final result/cascade action.
- Claude and Grok failures are rendered with their real compact HTTP/classification diagnostics when available; raw provider payloads and credentials remain hidden.
- Provider outputs pass a deterministic schema/identity validation boundary before they can enter the Shared Context Bridge.
- Bridge records are append-only, attributed to the authoritative room seat/provider/model, and treated as untrusted data.


## Bridge Read Fix
The transactional bridge now completes the post-response `BRIDGE_READ` handoff from committed Shared Context without exposing the bridge value in the provider input prompt or issuing a second provider request.


## Bridge Control Plane
The provider prompt now explicitly distinguishes the application-owned transactional bridge from model memory. For the explicit bridge test, DeepSeek emits a single bridge-write protocol record, Gemini emits a single bridge-read protocol record, and the application—not either model—performs commit, barrier, read resolution, and schema validation. The bridge value is never placed in Gemini input.


## Production Core
Request lifecycle, provider execution contract, strict Free Cascade #1→#10, timeout/retry policy, failure classification, actual-model attestation, round/shared-context state machines, transaction bridge guard, secret-safe audit events, and regression coverage.

## HOTFIX123.2 contract
Single-request determinism is enforced at the orchestration boundary. A Request ID may not be re-orchestrated while active and a completed Request ID is returned from its immutable in-chat result cache. Each round has one execution scope and each seat can be claimed once within that scope. Free Cascade attempts remain internal to the provider call and reuse the same Request ID + Round. Transactional Bridge creation therefore occurs once per Request ID + Round.

The live UI exposes authoritative telemetry in the form `model → classification → cascade action`; these values come from the provider attempt diagnostics rather than model-generated prose.


## HOTFIX127 — Execution Accounting / Attempt-Record Integrity
- Based on HOTFIX126; all existing files preserved.
- Worker/orchestration failures never synthesize provider Attempt #1 records.
- Authoritative counters distinguish configured/requested/executed/successful seats and cascade attempts.
- Provider execution audit events are emitted only from runtime execution events.
- Cascade attempts remain inside the same Request ID.
- No secrets or raw provider payloads are persisted.
