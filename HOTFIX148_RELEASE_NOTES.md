# HOTFIX148 — V26.3 ROOT-CAUSE CANONICAL COUNTER CLOSURE

Built additively from the complete HOTFIX147 package. No existing packaged files are deleted.

## Root-cause fix
The authoritative V26.3 historical audit previously computed `canonical_message_count` from the raw canonical `messages` list. That list can contain assistant/provider/synthesis/system artifacts. HOTFIX130 semantics require canonical conversation message identity to count only identity-bearing `role=user` MessageRecords.

The fix changes only the authoritative V26.3 audit projection so `canonical_message_count` uses the same identity semantics already enforced by the persistence layer and HOTFIX130 contract.

## Regression closure
Added regression coverage proving a mixed five-record canonical message list produces `canonical_message_count = 2`, while request/round counts remain unchanged.

## Preserved
- HOTFIX123.2 provider core and single-request determinism.
- HOTFIX129 Message→Request→Round persistence semantics.
- HOTFIX130 canonical counter semantics.
- HOTFIX147 security NO_RAW regression fix.
- No provider credentials, Secrets, explicit `*_FREE_MODELS`, provider endpoints, cascade ordering, Local Engine, Paid fallback, or automatic model selection changes.

## Validation
Full packaged pytest suite is executed before release.
