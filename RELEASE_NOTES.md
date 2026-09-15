# HOTFIX76-FINAL — DeepSeek V4.1 provider-routing identity correction

Version: `V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX76-FINAL`

## Surgical fixes
- Preserves the DeepSeek Free cascade and its explicit model order.
- Preserves API_ERROR → next-candidate behavior for DeepSeek.
- Keeps `execution_identity_mismatch` fail-closed for genuinely unrelated provider identities.
- Expands only the documented DeepSeek provider identity aliases needed after the September 14, 2026 routing change: the configured `deepseek-v4-flash` request may be served as `deepseek-flash` / V4.1-Flash, and `deepseek-v4-pro` requests may be routed to V4.1-Flash until V4.1-Pro is released.
- The main history/result invariant uses the same attestation function as the provider layer, preventing a valid documented provider-side routing identity from crashing the application after a successful response.
- No changes to Secrets, Local Engine, paid fallback, automatic model selection, or other providers.


## HOTFIX76 — DeepSeek provider identity invariant compatibility

- Fixed the runtime invariant in `main.py` to use the same DeepSeek identity-attestation matcher as the provider layer.
- Documented provider aliases such as `deepseek-flash` are accepted as the same executed model identity.
- Real unknown/mismatched DeepSeek identities remain fail-closed.
- No Secrets, model lists, cascade order, Local Engine, Paid fallback, or automatic model selection changes.
# HOTFIX76-FINAL — DeepSeek cascade + identity attestation correction

Version: `V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX76-FINAL`

## Surgical fixes
- DeepSeek HTTP/API failures remain non-terminal and advance from candidate #1 to candidate #2.
- DeepSeek HTTP-200 envelopes containing an `error` object are explicitly classified as `API_ERROR` before identity attestation, so they also advance through the Free cascade.
- The execution identity guard remains fail-closed: `execution_identity_mismatch` still stops the cascade.
- The documented current DeepSeek provider identity `deepseek-flash` is accepted as the provider identity for the configured `deepseek-v4-flash` request.
- No changes to Secrets, Local Engine, paid fallback, automatic model selection, or other providers.
