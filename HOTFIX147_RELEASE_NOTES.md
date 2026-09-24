# HOTFIX147 — V23 SECURITY + REGRESSION CLOSURE

## Scope — strictly limited

1. **Security:** close `NO_RAW_PROVIDER_PAYLOADS_IN_HISTORY` by treating sanitized/empty raw-payload field names as metadata and rejecting only retained non-empty raw payload values, including nested records.
2. **Regression Core:** restore and lock the HOTFIX130 compatibility APIs `_authoritative_ui_projection` and `_format_authoritative_counter_summary`, with counters sourced from persisted request metrics/results rather than UI message rows, agent prose, or latest-request projection.
3. **Release gate:** fail closed unless the full pytest suite is green and the HOTFIX147 security/regression contract is present.

## Explicitly unchanged

- Message → Request
- Request → Round
- Round sequence / canonical round identity
- canonical counter semantics
- `canonical_counter_source = CANONICAL_IDENTITY_RECORDS`
- HOTFIX123.2 single-request determinism / provider execution contract
- HOTFIX129 persistence contract
- HOTFIX130 authoritative result-counter semantics
- V26.3 canonical persistence design
- Free Cascade #1 → #10
- explicit `*_FREE_MODELS` model lists
- Official API-only execution contract
- no Local Engine
- no Paid fallback
- no automatic model selection
- Agent Prose is never authoritative
- UI message count is never authoritative

## Acceptance gate

The ZIP is rejected unless:

- `pytest = PASS`
- `security_audit = PASS`
- `NO_RAW_PROVIDER_PAYLOADS_IN_HISTORY = true`
- `canonical_counter_source = CANONICAL_IDENTITY_RECORDS`
- HOTFIX130 regression = PASS
- HOTFIX123.2 preservation = PASS
- HOTFIX129 preservation = PASS
- HOTFIX130 preservation = PASS

The release patch does **not** redesign Persistence.
