# HOTFIX27-FINAL

Version: `V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX27-FINAL`

## Scope
Built from the preserved full V22.1 release candidate. All existing test modules from the prior preserved baseline remain included; no test module was deleted. `gitops_layer.py` remains outside the application hotfix scope and is unchanged.

## Fixes and release hardening
1. Preserves the complete current test-file set (20 `test_*.py` modules) and enforces the exact set during source validation and ZIP verification.
2. Keeps the corrected 429 taxonomy: explicit quota/billing exhaustion is `QUOTA_EXCEEDED`; transient throttling is `RATE_LIMITED`.
3. Stops the Free-model cascade immediately on a confirmed authentication error, using the canonical public classification.
4. Keeps raw provider diagnostics transient and stores only compact classification summaries in visible History/session-state results.
5. Visible attempt diagnostics are compact and automatically expire after 60 seconds; raw provider payloads are never rendered.
6. Release tests execute in a fresh temporary copied sandbox with credential-like inherited environment variables scrubbed.
7. The exact packaged ZIP is re-extracted into a second fresh sandbox and the complete test suite is executed again before the artifact is accepted.
8. ZIP validation rejects unsafe paths and symlink members and checks the exact preserved test-file set.

## Preserved test modules
- test_attachments.py
- test_core.py
- test_entrypoint.py
- test_gitops_layer.py
- test_hardening.py
- test_hotfix13_model_identity.py
- test_hotfix14_cascade_invariants.py
- test_hotfix14_error_classification.py
- test_hotfix14_request_history_identity.py
- test_hotfix17_fixes.py
- test_hotfix18_fixes.py
- test_hotfix19_fixes.py
- test_hotfix21_release_consistency.py
- test_hotfix21_ui_privacy.py
- test_hotfix26_release_roundtrip.py
- test_provider_runtime.py
- test_v213_hardening.py
- test_v214_voice.py
- test_v215_resilience.py
- test_v216_hardening.py

## Explicit non-scope
`gitops_layer.py` remains exploratory/educational. No GitHub Push, PAT, GitHub App, or external repository mutation is performed by this release.
