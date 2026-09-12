# HOTFIX24-FINAL

Version: `V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX24-FINAL`

## Scope
Built from the current V22.1 release candidate while preserving the complete 19-module test suite. `gitops_layer.py` remains outside application hotfix scope and is unchanged.

## Fixes
1. Preserved all 19 existing test modules; the release builder now verifies the exact test-file set, not only a count.
2. Corrected 429 retry policy to use the same canonical classification as the public taxonomy: explicit quota/billing exhaustion is not retried; transient rate limiting remains retryable.
3. Raw provider diagnostics and raw result errors are consumed transiently and stripped before `last_results`/`last_diagnostics` persistence.
4. Visible attempt errors use only compact summaries and the existing 60-second TTL; raw provider payloads are never rendered.
5. Added regression coverage for session-state diagnostic privacy.
6. Release validation remains isolated in a temporary copied sandbox with credential-like environment variables scrubbed.

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
- test_provider_runtime.py
- test_v213_hardening.py
- test_v214_voice.py
- test_v215_resilience.py
- test_v216_hardening.py

## Explicit non-scope
`gitops_layer.py` remains exploratory/educational. No GitHub Push, PAT, GitHub App, or external repository mutation is performed by this release.
