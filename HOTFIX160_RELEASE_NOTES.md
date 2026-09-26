# HOTFIX160 — V26.3/V23 CANONICAL ROUND IDENTITY + MULTI-REQUEST REGRESSION CLOSURE

- Request creation owns canonical_round_base; first two requests allocate 1 then 2.
- Legacy zero/shifted round identities are normalized from canonical request order.
- Canonical RoundRecord is materialized with record_type=CANONICAL_ROUND_RECORD.
- message_ledger.record_message accepts round_id without creating a second identity source.
- Hydration/runtime indexes remain application-owned and rebuilt from canonical history.
- Bridge values are redacted at the provider boundary rather than injected into HTTP prompts.
- HOTFIX135 multi-request audit accepts two independent Requests and detects cross-request contamination/reuse.
- No Local Engine, no Paid fallback, and no implicit model selection are introduced.
