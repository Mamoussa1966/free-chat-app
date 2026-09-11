# V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX14

## HOTFIX14
- Preserves the complete previous project and test suite.
- Enforces authoritative `executed_model` identity across provider execution, round results, diagnostics, and AI-room rendering.
- Enforces Free API Cascade semantics: candidates are attempted in declared order and a successful candidate immediately terminates that provider's cascade; later candidates are not called after success.
- Adds request/round/seat result identity via `result_key` and regression coverage for cascade-stop invariants.
- Keeps the strict Free-only contract: no Local Engine, no paid fallback, and no automatic model selection.
- Streamlit Secrets remain authoritative when a non-empty Secret exists; Environment Variables are fallback-only.
- Release metadata is aligned to HOTFIX14, including application/provider version identifiers and the release builder default output name.
- Adds release-consistency regression coverage to prevent stale HOTFIX/version identifiers from reappearing in production source, documentation, or release tooling.
- Release is built only after syntax validation, full pytest execution, ZIP integrity validation, and manifest/hash generation.

## Verification
- Expected version: `V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX14`
- Free Cascade: `#1 → #10` per configured provider.
- No Local Engine.
- No paid fallback.
- No automatic model selection.
