# HOTFIX164.10 — Strict Bridge Security Audit Integration

## Purpose
Fix the live security-audit failure exposed by the HOTFIX164.9 two-message run. HOTFIX164.9 correctly moved strict Bridge proof out of provider result prose and into `bridge_runtime_evidence_store`, but `production_platform.security_audit()` still required `bridge_transaction_audit` inside provider results. That legacy expectation made an explicit strict Bridge request fail security audit even when the application-owned evidence ledger was complete.

## Changes
- `security_audit()` now validates strict live Bridge closure using only the application-owned `bridge_runtime_evidence_store`.
- Strict proof is rejected unless it is bound to the same Request ID and canonical Round ID/ordinal.
- The audit requires the full source/write/validate/commit/barrier/target-dispatch/target-response/read/match sequence, with each event bound to the expected Request and Round and with the expected status.
- The strict record must attest source execution, payload isolation, sanitized target representation, committed terminal state, sealed application-owned evidence, and exactly two Bridge trace records (one source write and one target read).
- Reusing a Bridge identity hash across strict requests within the same conversation fails the security gate.
- Missing, stale, malformed, partial, or provider-result-only proof remains `FAIL`; the patch does not synthesize PASS values.
- Legacy non-strict Bridge tests keep their previous result-audit compatibility path.
- Display label updated to HOTFIX164.10. The frozen provider identity and `VERSION.txt` are unchanged.

## Verification policy
Repository and archive round-trip test results establish artifact-level regression status only. The deployed application's live closure still requires the two-message test to produce complete request-bound evidence. After Message 2, use read-only Audit/Export only; do not send a third message.
