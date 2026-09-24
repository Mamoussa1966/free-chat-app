# HOTFIX147 — V23 SECURITY + REGRESSION CLOSURE

Additive closure release over HOTFIX146. This release addresses the three observed closure problems without reopening canonical persistence semantics.

## 1. Security false-positive closure
- Replaced substring-based raw-payload detection with structural, non-empty forbidden-field detection.
- User/provider prose containing labels such as `NO_RAW_PROVIDER_PAYLOADS_IN_HISTORY` is not treated as persisted payload evidence.
- Real persisted fields such as `raw_provider_payload`, `raw_payload`, `response_body`, and `provider_payload` remain fail-closed.
- Sensitive diagnostics receive the same structural treatment.

## 2. Regression Core closure
- Restored the HOTFIX130 authoritative UI projection API expected by the regression contract: `_authoritative_ui_projection`.
- Restored `_format_authoritative_counter_summary`.
- Added regression tests for the exact contract.

## 3. Persistence/counter semantic closure
- No changes to Message→Request.
- No changes to Request→Round.
- No changes to round sequence or identity.
- No changes to HOTFIX130 canonical counter semantics.
- UI message count remains explicitly non-authoritative.
- Canonical counts remain sourced from `V26_3_CANONICAL_CONVERSATION_STORE`.

## Verification
- Source tree pytest: PASS.
- Re-extracted ZIP pytest: PASS.
- The release gate is fail-closed and does not permit a release when tests fail.

## Explicitly preserved
HOTFIX123.2 · HOTFIX129 · HOTFIX130 · provider execution contract · Free Cascade controller · official API-only policy · no Local Engine · no Paid fallback.
