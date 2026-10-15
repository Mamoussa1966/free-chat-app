# HOTFIX164.25 targeted regression cases
Status: SPECIFICATION / FIXTURE DATA ONLY. IDs below are synthetic and must never be entered as live evidence.

## Synthetic fixture IDs
- `TEST-HF16425-REQ-001`
- `TEST-HF16425-REQ-002`
- `TEST-HF16425-REQ-MISSING`
- `TEST-HF16425-MSG-001`
- `TEST-HF16425-ROUND-001`
- `TEST-HF16425-BRIDGE-001` (label only; not Bridge proof)

## Test cases
1. `test_no_existing_chat_is_not_proven`
   - Input: no matching active chat in session state.
   - Assert: NOT_PROVEN, `NO_EXISTING_CANONICAL_CONVERSATION`; no new chat/state records.
2. `test_empty_ledgers_do_not_pass_counter_closure`
   - Input: existing canonical conversation with empty messages/requests/rounds.
   - Assert: NOT_PROVEN; empty counts cannot qualify as closure evidence.
3. `test_no_targets_does_not_auto_select`
   - Input: targets `("", "")`.
   - Assert: NO_TARGETS, `NO_EXPLICIT_TARGETS_PROVIDED`; no generated or latest-N IDs.
4. `test_unknown_request_id_is_not_proven`
   - Input: target `TEST-HF16425-REQ-MISSING` against a fixture without that ID.
   - Assert: target not found, NOT_PROVEN/FAIL according to existing contract; no fallback selection.
5. `test_message_request_round_identity_chain_must_match`
   - Input: fixture with `TEST-HF16425-MSG-001` bound to `TEST-HF16425-REQ-001`, but Round is bound to `TEST-HF16425-REQ-002`.
   - Assert: FAIL; report the exact identity mismatch.
6. `test_duplicate_request_ids_fail_closed`
   - Input: duplicate canonical Request IDs.
   - Assert: FAIL; no deduplication that hides the conflict.
7. `test_missing_bridge_evidence_never_passes`
   - Input: target Request exists, but application-owned Bridge evidence is absent.
   - Assert: strict-live Bridge status NOT_PROVEN/FAIL, never PASS.
8. `test_audit_is_read_only`
   - Fingerprint the chat before/after.
   - Assert: identical fingerprints; no Requests/Rounds/Bridges/events created.
9. `test_no_provider_dispatch`
   - Replace provider dispatch functions with test sentinels that raise if called.
   - Assert: audit completes without calling them.
10. `test_valid_nonempty_fixture_only_passes_identity_preflight`
    - Input: consistent nonempty Message→Request→Round fixture.
    - Assert: identity preflight may pass, but strict-live Bridge closure remains NOT_PROVEN unless valid application-owned Bridge evidence is supplied.

## Suggested user-visible test messages
Use these only in a test/staging environment. Do not send them as production Council messages merely to manufacture evidence.

A. `HOTFIX164.25 REGRESSION A — READ-ONLY EMPTY-STATE GUARD. Inspect existing canonical history only. Do not create a Message, Request, Round, Bridge, provider call, or fallback identity. Return NOT_PROVEN if no existing canonical conversation or if all canonical ledgers are empty.`

B. `HOTFIX164.25 REGRESSION B — IDENTITY CHAIN. Audit only the explicit synthetic fixture target TEST-HF16425-REQ-001. Verify Message→Request→Round binding. Do not treat this synthetic ID as a live application record.`

C. `HOTFIX164.25 REGRESSION C — MISSING BRIDGE. For fixture target TEST-HF16425-REQ-002, evidence is intentionally absent. Assert strict-live Bridge closure remains NOT_PROVEN; do not invoke a provider or fabricate evidence.`

D. `HOTFIX164.25 REGRESSION D — UNKNOWN TARGET. Audit TEST-HF16425-REQ-MISSING. Do not auto-select another Request. Return NOT_PROVEN/FAIL with an explicit target-not-found blocker.`

E. `HOTFIX164.25 REGRESSION E — NO SIDE EFFECTS. Capture state fingerprint, run the read-only audit, and prove that canonical counts, request/round/bridge records, and runtime execution events remain unchanged.`

## Important distinction
The synthetic IDs above are for deterministic automated tests only. They are not real Request IDs and cannot prove live Bridge execution. For a live audit, copy a Request ID from an existing authoritative canonical RequestRecord in the actual deployed conversation.
