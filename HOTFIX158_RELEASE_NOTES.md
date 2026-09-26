# HOTFIX158 — CANONICAL ROUND RECORD / IDENTITY EVIDENCE CLOSURE

Scope: canonical round identity only. Existing UI, provider, Free Cascade, security, persistence, synthesis, and mobile composer behavior is preserved.

## Closure contract
Every runtime-created canonical RoundRecord is materialized before provider dispatch with:
- `record_type = CANONICAL_ROUND_RECORD`
- `round_id = <conversation_id>:<request_id>:r<ordinal>`
- `canonical_round_record_id = round_id`
- `canonical_identity_key = <conversation_id>:<request_id>:r<ordinal>`
- `conversation_id`
- `request_id`
- `message_id`
- `ordinal`
- `round`
- `round_identity_contract = V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1`

The authoritative audit proves these values directly from the canonical ConversationRecord. `round_1_ids` is never used as proof.

## Regression
- Existing full regression suite: 541 passed before the HOTFIX158 runtime-materialization regression was added.
- HOTFIX158 adds a direct runtime test proving `begin_round()` materializes the canonical RoundRecord and that its conversation/request/ordinal identity is persisted.
