# HOTFIX149 — V26.3 ROOT CAUSE REQUEST→ROUND IDENTITY / ATOMIC ALLOCATION CLOSURE

## Scope
- Fixes the remaining canonical Request→Round binding defect observed after HOTFIX148.
- Round ordinal allocation now occurs once at authoritative Request creation and is persisted on the canonical RequestRecord.
- Provider execution/completion order, rerun order, and round-record list order cannot reassign a Request's Round ordinal.
- `round_id` remains derived from the immutable conversation/request identity plus the allocated canonical round ordinal.
- Message→Request identity is preserved.
- Canonical counts remain application-owned and are not derived from UI, provider prose, or latest-request projections.

## Contract
`V26.3.21-REQUEST-CREATION-MONOTONIC-ROUND/v1`

## Required two-turn proof
- REQUEST_1 → ROUND_1 = TRUE
- REQUEST_2 → ROUND_2 = TRUE
- REQUEST_2 → ROUND_1 = FALSE
- canonical_round_ordinals = [1,2]
- canonical_round_sequence_base = 1
- canonical_round_sequence_proven = TRUE

## Regression protection
- Existing HOTFIX148/V26.3 canonical counter tests retained.
- New tests cover reversed completion/commit ordering and immutable Request-time Round allocation.
- No provider, model list, Secret, Local Engine, Paid fallback, Bridge, or HOTFIX123.2 execution contract changes.
