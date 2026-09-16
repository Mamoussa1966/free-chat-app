# AI Council — Free Cascade

V22.1-HOTFIX87-PRODUCTION-HARDENED

Free API Cascade #1→#10. No Local Engine, no paid fallback, and no implicit model selection.

HOTFIX87 adds a real round-scoped Shared Context Bridge. Each successful provider response is appended as untrusted reference data before the next provider call. Trusted seat/provider/executed-model identity remains authoritative and cannot be overridden by bridge content.

DeepSeek is first in bridge execution order to allow a direct DeepSeek 7 → Gemini 2 bridge test within one round. The displayed result order remains the canonical room-seat order.


HOTFIX87 bridge correction: explicit `BRIDGE_* = value` declarations in the current request are promoted into the round-scoped bridge as untrusted test data before the first provider call. Provider outputs can also emit an explicit `BRIDGE_WRITE: BRIDGE_* = value` line, which is appended to the bridge with source-seat attribution. Trusted seat/provider/model identity remains separate and authoritative. Do not use BRIDGE_* declarations for API keys or real secrets.

HOTFIX87 production hardening: provider outputs are schema-validated before bridge promotion; each attempt exposes safe telemetry (attempt/model/HTTP status/classification/retryable/latency/request ID/round/final result); provider failures are isolated so later seats continue; raw payloads and credentials remain excluded from UI/history.


## HOTFIX87 — Structured Bridge Write
The SharedContextBridge now normalizes explicit provider bridge writes into canonical attributed records. The intended proof path is Seat 7 → DeepSeek → Bridge Write → Shared Context → Gemini → Seat 2 → Bridge Read. This change does not modify provider adapters or the seat/identity/Free Cascade contract.
