# HOTFIX82 — Central Seat Identity / Shared Context Hardening

V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX82-FINAL

- Centralizes trusted Seat Identity for all API seats 1–5, 7, and dynamic seats 8–20.
- Separates trusted runtime identity from untrusted shared conversation context.
- Prevents shared content from overriding room seat, provider identity, API mode, or executed model.
- Preserves the existing cascade, Secrets precedence, no Local Engine, no paid fallback, and unlimited provider response-time contract.
- Adds explicit identity metadata to runtime results for diagnostics and verification.

# HOTFIX82-FINAL — DeepSeek cascade + identity attestation correction

Version: `V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX82-FINAL`

## Surgical fixes
- DeepSeek HTTP/API failures remain non-terminal and advance from candidate #1 to candidate #2.
- DeepSeek HTTP-200 envelopes containing an `error` object are explicitly classified as `API_ERROR` before identity attestation, so they also advance through the Free cascade.
- The execution identity guard remains fail-closed: `execution_identity_mismatch` still stops the cascade.
- The documented current DeepSeek provider identity `deepseek-flash` is accepted as the provider identity for the configured `deepseek-v4-flash` request.
- No changes to Secrets, Local Engine, paid fallback, automatic model selection, or other providers.

HOTFIX82 — DeepSeek identity invariant hardening
- Fixes main.py NameError by importing the DeepSeek identity matcher used by the UI.
- Applies the same documented DeepSeek identity alias normalization to the council success invariant.
- Keeps strict identity attestation for unknown/mismatched DeepSeek identities.
- No changes to other providers, Secrets, Local Engine, paid fallback, automatic selection, or model catalog order.
