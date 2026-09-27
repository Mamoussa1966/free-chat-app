# HOTFIX160 — V26.3/V23 CANONICAL ROUND IDENTITY + MULTI-REQUEST REGRESSION CLOSURE

- Request creation now owns `canonical_round_base` from canonical Request identity records.
- Fresh requests allocate Round 1, then Round 2, without completion-order/UI-counter dependence.
- Canonical Round records are materialized before provider execution with immutable `round_number`, `ordinal`, `record_type`, `canonical_round_record_id`, and `canonical_identity_key`.
- Legacy one-round-per-request histories are normalized from canonical Request creation order only.
- Multi-request isolation remains Request-scoped; Request IDs, Round IDs, and Bridge IDs are never reused across requests.
- Historical compatibility audit paths accept canonical Round-only evidence when no canonical Request list exists, while the full Request→Round contract remains strict whenever Request records are present.
- No Local Engine, no paid fallback, no implicit model discovery, and no provider model-list mutation.
