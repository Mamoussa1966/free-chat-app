# HOTFIX128 — PERSISTENCE TEST CONTRACT CORRECTION / FINAL

## Purpose
HOTFIX128 makes one and only one correction above HOTFIX127: the active V26.3 Persistence test contract now uses the correct positive mapping **REQUEST_2 → ROUND_2**. The old **REQUEST_2 → ROUND_1** wording is retained only in historical release notes where it describes older defects/tests; it is not an active positive acceptance condition.

## Engineering scope
- No Provider Core change.
- No Free Cascade change.
- No Secrets change.
- No Model List change.
- No Bridge implementation change.
- No canonical persistence engine behavior change.
- No identity-generation change.
- Only the authoritative test-contract artifact and its regression gate are added.

## Active contract
`MESSAGE_1 → REQUEST_1 → ROUND_1`

`MESSAGE_2 → REQUEST_2 → ROUND_2`

Negative control:
`REQUEST_2 → ROUND_1 = FALSE`

## Fail-closed regression
The HOTFIX128 test suite verifies that an intentionally corrupted Request 2 → Round 1 canonical record cannot pass the authoritative gate. It must produce `request_2_round_2_mapping=false`, `canonical_round_sequence_proven=false`, and a non-PASS authoritative result.

## Historical compatibility
Older HOTFIX116/HOTFIX119/HOTFIX121 notes may contain the obsolete positive `REQUEST_2 → ROUND_1` wording because those files are historical evidence and are preserved byte-for-byte. HOTFIX128 does not reinterpret those historical notes as the current contract.

## Release acceptance
1. Preserve every HOTFIX127 packaged file.
2. Add only HOTFIX128 contract/gate/version/test artifacts.
3. Run the complete pytest suite.
4. Re-extract the exact ZIP.
5. Run the complete pytest suite against the re-extracted release.
6. Verify ZIP member uniqueness and SHA-256.
7. Verify the active contract contains `REQUEST_2 → ROUND_2` as the positive mapping and `REQUEST_2 → ROUND_1 = FALSE` only as the negative control.
