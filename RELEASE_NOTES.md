# HOTFIX84 — Shared Context Bridge Write/Read Correction

`V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX84-FINAL`

## Surgical change
- Built directly from the Library previous release-MULTIAGENT-FINAL ZIP.
- Adds a round-scoped, append-only `SharedContextBridge` in `main.py`.
- Successful provider output is appended to the bridge before the next provider call in the same round.
- DeepSeek is executed first in the bridge order so a DeepSeek 7 -> Gemini 2 bridge test can be observed in one round; final UI/history order remains canonical room-slot order.
- Bridge entries are explicitly marked as `UNTRUSTED DATA` and cannot override authoritative seat/provider/model identity.
- Preserves Free API Cascade #1->#10, Secrets precedence, no Local Engine, no paid fallback, no automatic model selection, and the existing provider contracts.
- Adds regression tests proving provider-to-provider bridge propagation and identity separation.

## Explicit non-scope
- No credential values are packaged.
- No provider model catalog is changed.
- No GitHub push or repository mutation is performed.


## HOTFIX84 — Bridge correction
- Preserves HOTFIX84 provider ordering, identity isolation, Free Cascade, and no-Local/no-paid contract.
- Adds a narrow `BRIDGE_* = value` declaration parser so an explicit Shared Context write request becomes actual round-scoped bridge data before provider calls.
- Adds an optional `BRIDGE_WRITE: BRIDGE_* = value` provider write protocol with source-seat attribution.
- Provider identity is never read from bridge data.
- BRIDGE_* values are explicitly test/reference data and must not be used for API credentials or real secrets.
