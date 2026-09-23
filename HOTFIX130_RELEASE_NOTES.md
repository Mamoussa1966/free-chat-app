# HOTFIX130 — CANONICAL PERSISTENCE COUNTER CONSISTENCY

Built directly from HOTFIX129 without deleting any existing packaged file.

## Problem fixed
HOTFIX129 correctly established the two-real-turn persistence contract, but runtime output could still show two different meanings for "message count":

- authoritative historical audit: identity-bearing user MessageRecords;
- `v26_3_persistence`: raw length of the canonical messages list.

That allowed a conversation containing two user turns plus provider/synthesis message artifacts to report `canonical_message_count = 2` and `persisted_message_count = 5`.

## Surgical fix
`conversation_persistence_v26.persistence_audit()` now derives Message/Request/Round counts from the same canonical identity semantics used by the authoritative audit. Raw list lengths are no longer authoritative.

## Required runtime result
A valid two-turn canonical conversation must report:

- `canonical_message_count = 2`
- `persisted_message_count = 2`
- `canonical_request_count = 2`
- `persisted_request_count = 2`
- `canonical_round_count = 2`
- `persisted_round_count = 2`
- `counter_semantics_consistent = TRUE`
- `canonical_round_ordinals = [1, 2]`
- `canonical_round_sequence_proven = TRUE`
- `REQUEST_2 → ROUND_2 = TRUE`
- `REQUEST_2 → ROUND_1 = FALSE`

## Verification
The release gate requires the full HOTFIX129 regression suite, plus dedicated counter-consistency tests, source/re-extracted ZIP verification, baseline member preservation, and an explicit regression containing three non-user message artifacts so raw list length cannot silently become authoritative again.
