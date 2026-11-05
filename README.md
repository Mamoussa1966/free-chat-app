# AI Council — Free Cascade

V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE

HOTFIX123 adds an application-owned Production Chat Reliability layer + Production Core Test Runner. Use **🧪 Run Production Core Tests** in the sidebar; the application executes the local Test Harness and renders the real PASS/NO-GO result. AI providers are not asked to run pytest.

## Current zero-cost production policy

No Local Engine, no paid fallback, and no implicit model selection. A setting named `*_FREE_MODELS` is only a model-list configuration; it is **not** proof that the vendor's API is free.

- Gemini is eligible only after the operator explicitly sets `GEMINI_API_ZERO_COST_CONFIRMED=true` after verifying the Google AI Studio project is on the Free Tier and is not attached to paid billing. Until then, Gemini text and voice requests are blocked before network dispatch.
- The approved Gemini model IDs are `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`, and `gemini-3.1-flash-lite`. Older, unavailable, or unpriced aliases are filtered out.
- An optional **GroqCloud** agent can be added as dynamic seat 8 using the official Groq OpenAI-compatible Chat Completions endpoint. This is **not** the existing xAI Grok seat 4. It requires a separate `GROQ_CLOUD_API_KEY`, explicit `GROQ_CLOUD_FREE_MODELS`, and `GROQ_CLOUD_FREE_PLAN_CONFIRMED=true` only after checking that the Groq account remains on the Free Plan. The current allowlist is limited to `openai/gpt-oss-120b` and `openai/gpt-oss-20b`, which appear in Groq's published Free Plan rate-limit table. The Free Plan has daily limits; exceeding them should return a rate-limit response. Do not upgrade the account to Developer or enable paid usage.
- OpenAI, Claude, xAI Grok, Kimi, DeepSeek, and every other dynamic seat remain blocked from production API dispatch by default. A configured key or a `*_FREE_MODELS` string cannot unlock them.
- A model is added to an allowlist only after its provider publishes an explicit no-cost API allowance for that exact model and the account tier is checked. Promotional credits, free chat-app subscriptions, playground access, or trial credits do not qualify.

This is a fail-closed billing safeguard. The confirmation settings are operator attestations, not live billing-state verification APIs; they must be set only after checking the provider console. No Paid fallback or automatic model discovery is allowed.

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
