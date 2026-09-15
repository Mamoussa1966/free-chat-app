# HOTFIX79

- Fix DeepSeek identity attestation for the provider's current canonical `deepseek-flash` / V4.1 Flash identity when the configured legacy `deepseek-v4-flash` is routed by DeepSeek.
- Accept the documented current Flash identity for configured `deepseek-v4-pro`, which DeepSeek now routes to V4.1 Flash after 2026-09-14.
- Preserve fail-closed identity checks for genuinely unrelated/mismatched models.
- Fix the main council history invariant so it uses the same provider-specific attestation rule instead of requiring literal string equality.
- No changes to Secrets, other providers, Local Engine, Paid fallback, or automatic model selection.

# HOTFIX79-FINAL — DeepSeek cascade + identity attestation correction

Version: `V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX79-FINAL`

## Surgical fixes
- DeepSeek HTTP/API failures remain non-terminal and advance from candidate #1 to candidate #2.
- DeepSeek HTTP-200 envelopes containing an `error` object are explicitly classified as `API_ERROR` before identity attestation, so they also advance through the Free cascade.
- The execution identity guard remains fail-closed: `execution_identity_mismatch` still stops the cascade.
- The documented current DeepSeek provider identity `deepseek-flash` is accepted as the provider identity for the configured `deepseek-v4-flash` request.
- No changes to Secrets, Local Engine, paid fallback, automatic model selection, or other providers.
