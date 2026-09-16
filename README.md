# AI Council — V22.1-HOTFIX87-PRODUCTION-HARDENED

`V22.1-HOTFIX87-PRODUCTION-HARDENED` is a hardened production release built from the only available project artifact (the prior prior_bridge_baseline codebase).

## Contract preserved
- Seat identity and provider identity remain authoritative and immutable.
- Explicit `*_FREE_MODELS` only; Free Cascade remains #1 → #10 per provider.
- Official API only. No Local Engine. No Paid fallback. No automatic model selection.
- Streamlit Secrets retain priority over environment variables when non-empty.
- Shared Context remains untrusted reference data and cannot redefine identity, credentials, or model selection.

## HOTFIX87 reliability layer
Every Free Cascade candidate emits a structured public-safe attempt record containing:
- Provider
- Attempt number
- Model
- HTTP status (exact when available; `2xx` on successful responses)
- Error classification
- Retryable
- Execution latency
- Request ID
- Round
- Final result

Raw provider payloads, credentials, and secret values are never persisted into UI/history telemetry.

## Provider isolation
Each provider owns its own Free Cascade. Authentication, quota, model-unavailable, and other provider failures are classified at the provider boundary and cannot silently redefine another provider's identity or cascade. A failing provider is isolated from other provider seats.

## Structured Shared Context Bridge
Provider output is processed at the Bridge boundary:

`Provider Output → Schema Validation → Bridge Record → Shared Context → Next Provider → Validation`

Only explicit `BRIDGE_WRITE: BRIDGE_* = value` records are promoted to structured Bridge records. Bridge records are attributed to source seat/provider/executed model and remain untrusted data.

## Architectural target
`Seat 7 → DeepSeek → Bridge Write → Shared Context → Gemini → Seat 2 → Bridge Read`

The bridge execution order is deterministic for this source/consumer path, while UI/history output remains in canonical seat order.
