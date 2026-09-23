# HOTFIX130 — CANONICAL PERSISTENCE COUNTER CONSISTENCY GATE

## Root cause
HOTFIX129 proved the two-real-turn lifecycle but exposed a semantic counter split: the authoritative historical audit counted identity-bearing user MessageRecords, while `v26_3_persistence.persisted_message_count` used the raw length of the canonical `messages` list. The latter can contain non-user/provider artifacts, so a valid two-turn conversation could report `canonical_message_count = 2` while `persisted_message_count = 5`.

## Fix
There is now one counter definition for the persistence contract:

- Message count = canonical records with a valid `message_id` and `role == user`.
- Request count = canonical records with a valid `request_id`.
- Round count = canonical records with a valid `round_id`.

The persistence audit and authoritative historical audit must derive their counts from these same canonical identity records. Raw list length is never authoritative.

## Required invariant
For every loaded canonical ConversationRecord:

`persisted_message_count == canonical_message_count`

`persisted_request_count == canonical_request_count`

`persisted_round_count == canonical_round_count`

and:

`counter_semantics_consistent = TRUE`

## Fail closed
If the canonical store cannot be loaded, all authoritative counts are `NOT_PROVEN`.

No UI projection, Agent Prose, timestamp ordering, synthesis record, or raw list length may be used to manufacture a count.

## Preservation
HOTFIX130 is a surgical patch over HOTFIX129. Provider Core, Free Cascade, official API-only policy, Bridge behavior, Secrets handling, model configuration, and HOTFIX129's two-real-turn lifecycle are unchanged.
