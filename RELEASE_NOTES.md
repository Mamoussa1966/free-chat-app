# V22.1-FINAL-EXACT-NAMES-UPDATED-HARDENED-HOTFIX8

- Streamlit Secrets are now an absolute authority when the exact key exists, including an intentionally empty key; stale environment values can no longer shadow it.
- Added an in-app Secrets reload action and non-secret model-source diagnostics.
- Preserved the strict Free-only cascade, 10-model cap, Unicode mobile separator handling, and no Local Engine / paid fallback contract.
- Added regression coverage for an empty authoritative Secret blocking a stale environment model list.

# V22.1-FINAL-EXACT-NAMES-UPDATED-HARDENED-HOTFIX6

- Fixes the deployed-version/configuration mismatch: the active provider layer reads `*_FREE_MODELS` directly from Streamlit Secrets on every Streamlit run.
- Streamlit Secrets are authoritative; environment variables are used only when the exact Secret is absent or empty.
- No implicit model catalog, hard-coded Gemini fallback, or paid/local fallback is injected into an explicitly configured Free cascade.
- Mobile Unicode separators such as `‚`, `،`, `，`, and `؛` are normalized safely at the configuration boundary.
- Maximum cascade length is exactly 10 candidates per provider.
- Active model candidates, source labels, and a non-secret configuration fingerprint are exposed for deployment diagnostics without exposing credentials.
- Preserves the complete test set from the prior release; release packaging excludes caches, bytecode, nested ZIPs, and manifests from the payload.
- Current Streamlit UI must show provider version `V22.1-FINAL-EXACT-NAMES-UPDATED-HARDENED-HOTFIX6` after this release is deployed.
