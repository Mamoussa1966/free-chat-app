# HOTFIX150 — CANONICAL REQUEST→ROUND IDENTITY BINDING CLOSURE

HOTFIX150 is a narrow additive closure on top of HOTFIX149.

## Scope
- Preserves HOTFIX147/HOTFIX148/HOTFIX149 files and behavior.
- No Secrets, model, Free Cascade, provider-adapter, seat-count, synthesis, UI-label, or canonical counter changes.
- `canonical_message_count`, `canonical_request_count`, and `canonical_round_count` are unchanged.
- Historical identity selection no longer uses `created_at`, list order, latest-request projection, or agent prose.
- The authoritative audit orders persisted turns by the canonical RoundRecord ordinal and binds each RoundRecord directly to its persisted `request_id` and `message_id`.
- The round ID numeric suffix must equal the canonical `round` ordinal; mismatch fails closed.

## Regression fixture
The HOTFIX150 gate includes the exact failure pattern observed in the prior runtime evidence: two valid Message→Request bindings with Request/Round identity inverted. The fixture must remain `NOT_PROVEN` rather than being normalized or reconstructed.

## Required runtime path
TURN 1 → persist → Streamlit rerun → TURN 2 → persist → Streamlit rerun → reload canonical store → rebuild indexes → authoritative audit.

## Proof target
A correct canonical graph must prove:
- Message 1 → Request 1
- Message 2 → Request 2
- Request 1 → Round 1
- Request 2 → Round 2
- Request 2 → Round 1 = FALSE
- canonical round ordinals are `[1, 2]`
- sequence base is `1`
- canonical round sequence is proven
- agent prose is not identity/counter source
