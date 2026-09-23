# HOTFIX127 — AUTHORITATIVE ROUND CONTRACT CORRECTION / FINAL PERSISTENCE GATE

## Purpose
HOTFIX127 is the corrective release immediately after HOTFIX126. It closes the final contract defect identified during the real V26.3 historical persistence test: the required mapping is **Request 2 → Round 2**, not Request 2 → Round 1.

## Canonical contract
The production persistence proof is now mechanically derived from the Application-Owned canonical conversation store:

`Message 1 → Request 1 → Round 1`

`Message 2 → Request 2 → Round 2`

and the negative control must prove:

`Request 2 → Round 1 = FALSE`

No audit label, UI text, provider prose, synthesis text, or narrower current-request ledger may promote a mapping to PASS.

## HOTFIX127 hardening
1. Each selected historical MessageRecord must have exactly one canonical RequestRecord binding.
2. Each selected Message→Request→Round chain must have exactly one canonical RoundRecord.
3. `RoundRecord.message_id`, `request_id`, `conversation_id`, and `session_id` must match the canonical parent records.
4. `RoundRecord.round` must equal the expected monotonic ordinal.
5. The numeric `round` must equal the `:rN` suffix of `round_id`.
6. `round_identity_contract` must equal `V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1`.
7. The exact two-message contract requires exactly two canonical user messages, two canonical requests, and two canonical rounds.
8. Duplicate Request bindings are ambiguous and fail closed; the audit never selects the latest duplicate to manufacture proof.
9. Extra/duplicate RoundRecords fail the exact historical contract.
10. A corrupted Request 2 → Round 1 record must produce `request_2_round_2_mapping=false`, `canonical_round_sequence_proven=false`, and `conversation_runtime_audit=FAIL`.
11. The authoritative audit exposes `canonical_round_identity_evidence` so the proof can be inspected as record-level evidence rather than inferred from labels.
12. Provider Core, Free Cascade, Secrets, Model Lists, Bridge semantics, and API credentials are unchanged by this release.

## Regression philosophy
The release is fail-closed: missing, ambiguous, contradictory, or corrupted canonical identity is `NOT_PROVEN`/`FAIL`; it is never repaired from agent prose or a UI projection.

The design uses canonical, deterministically verifiable identity relationships rather than presentation projections.

## Release acceptance
- Preserve every file from HOTFIX126.
- Run the full pytest suite.
- Re-extract the generated HOTFIX127 ZIP.
- Run the full pytest suite against the re-extracted release tree.
- Verify ZIP member uniqueness and SHA-256.
- Verify all HOTFIX127 regression cases pass.
