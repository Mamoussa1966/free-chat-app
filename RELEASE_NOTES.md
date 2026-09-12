# V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX14

## HOTFIX14
- Adds a permanent per-chat request/round/seat identity ledger; `(request_id, round, seat)` must remain unique across the full retained History, independent of the displayed model or round number.
- Assigns a unique execution `request_id` to every accepted request while keeping the request fingerprint solely for exact duplicate-submission detection.
- Displays stable `Request N · Round R` numbering so two distinct requests using the same provider/model/round cannot appear as one repeated request.
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


## HOTFIX14 diagnostic hardening
- Every failed Free-cascade candidate is now recorded as `attempt_diagnostics` with candidate number, exact model, HTTP status when available, stable `error_class`, sanitized error text, and whether the cascade may advance.
- Failed attempts are persisted into the successful assistant History entry, so the UI can show why #1/#2 failed while still showing the actual executed model.
- No cascade ordering or fallback policy was changed: candidates remain explicit `*_FREE_MODELS` entries and execution stops at the first successful candidate.
