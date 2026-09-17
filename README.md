# AI Council — Free Cascade

V22.1-HOTFIX99-PRODUCTION-HARDENED

HOTFIX99 adds an application-owned Production Core Test Runner. Use **🧪 Run Production Core Tests** in the sidebar; the application executes the local Test Harness and renders the real PASS/NO-GO result. AI providers are not asked to run pytest.

Free API Cascade #1→#10. No Local Engine, no paid fallback, and no implicit model selection.

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
