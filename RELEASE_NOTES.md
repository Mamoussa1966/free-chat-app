# HOTFIX74-FINAL — DeepSeek cascade + identity attestation correction

Version: `V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX74-FINAL`

## Surgical fixes
- DeepSeek HTTP/API failures remain non-terminal and advance from candidate #1 to candidate #2.
- DeepSeek HTTP-200 envelopes containing an `error` object are explicitly classified as `API_ERROR` before identity attestation, so they also advance through the Free cascade.
- The execution identity guard remains fail-closed: `execution_identity_mismatch` still stops the cascade.
- The documented current DeepSeek provider identity `deepseek-flash` is accepted as the provider identity for the configured `deepseek-v4-flash` request.
- No changes to Secrets, Local Engine, paid fallback, automatic model selection, or other providers.
