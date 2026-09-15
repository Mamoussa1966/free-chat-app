
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


# HOTFIX76-FINAL — DeepSeek identity guard consistency

Version: `V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX76-FINAL`

## Surgical fixes
- Fixed the remaining strict DeepSeek identity comparison in `main.py` history rendering.
- Both the execution path and the history/UI path now use the same `_deepseek_model_identity_matches()` attestation rule.
- `deepseek-v4-flash` with provider-reported `deepseek-flash` is accepted as the documented current DeepSeek identity.
- Unknown identities such as `some-random-model` remain fail-closed as `execution_identity_mismatch`.
- DeepSeek `API_ERROR` remains non-terminal and advances to the next explicitly configured Free candidate.
- No changes to Secrets, model lists, cascade order, Local Engine, paid fallback, automatic model selection, or other providers.
