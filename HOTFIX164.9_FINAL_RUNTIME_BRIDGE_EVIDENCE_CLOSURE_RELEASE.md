# HOTFIX164.9 — Final Application-Owned Bridge Runtime Evidence Closure

## Purpose
Correct the Bridge proof/observability gaps found in the HOTFIX164.8 live export without changing the frozen provider identity or manufacturing test success.

## Changes

- A strict live Bridge request obtains its `BRIDGE_RESULT` from one successfully attested DeepSeek / Seat 7 provider execution. Provider-output parsing is not allowed to create a duplicate source write in strict mode.
- Strict Bridge provider execution is dependency-ordered: DeepSeek source first, then Gemini target. Gemini dispatch is suppressed unless the request-bound source result is committed and the barrier is open.
- The application-owned lifecycle sequence must be exactly `SOURCE_EXECUTION → WRITE → VALIDATE → COMMIT → BARRIER → TARGET_DISPATCH → TARGET_RESPONSE → READ → MATCH`.
- Runtime Bridge evidence now records the canonical Round ID in addition to the ordinal. The production persistence and two-request regression audits require the Bridge evidence to match the canonical Request/Round binding.
- Strict Bridge metrics take identity only from the request-scoped application-owned runtime evidence store, never from result-prose/audit projections. A missing or incomplete record yields `NOT_PROVEN` / `FAIL`, not a vacuous PASS.
- Runtime export includes a safe Bridge evidence projection and canonical Round rows. It redacts raw Bridge IDs and excludes Bridge values, secrets, and raw HTTP payloads.
- Production Bridge closure gates require the Bridge runtime gate itself to be `PASS`, complete source/target/HTTP-payload isolation evidence, the committed terminal state, and a canonical Round binding.
- The displayed hotfix label is updated to HOTFIX164.9. Frozen `VERSION.txt`, `HOTFIX_RELEASE_VERSION`, and `PLATFORM_RELEASE_VERSION` contracts remain unchanged.

## Verification policy

Repository tests and ZIP round-trip tests validate the code and artifact only. They do not attest that a deployed application has completed a live Bridge transaction. Live closure remains proven only when the deployed HOTFIX164.9 application produces complete application-owned evidence for the existing two-message test. After Message 2, use read-only Audit/Export only; do not submit a third message to manufacture additional evidence.
