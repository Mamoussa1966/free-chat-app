# HOTFIX126 — AUTHORITATIVE ROUND IDENTITY / PRODUCTION REGRESSION GATE

## Scope
Built from HOTFIX125 without deleting or narrowing the packaged project tree. The frozen Provider Core remains V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE.

## Final fixes
1. Conversation Round identity is monotonic across independent Requests: Message 1 → Request 1 → Round 1; Message 2 → Request 2 → Round 2 when each Request executes one round.
2. `RoundRecord.round`, the `:rN` suffix in `round_id`, and `V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1` must agree in Application-Owned canonical state.
3. Historical audit has no legacy compatibility PASS path for this regression: missing or contradictory Round evidence is NOT_PROVEN/FAIL and cannot be Production-ready.
4. Production readiness treats the authoritative Round Identity Gate as mandatory.
5. Bridge semantics remain strict: no Bridge Test requested → `NOT_REQUESTED`, never Bridge FAIL merely because Bridge was not requested; Bridge Test requested → all required Bridge proof conditions must pass or the gate FAILs.
6. Canonical history hashing includes the Round identity contract marker, so contract tampering changes the authoritative digest.
7. Existing packaged files are preserved; manifest is regenerated from the actual ZIP contents.

## Release acceptance
The exact ZIP is re-extracted and the full pytest suite is run before release.
