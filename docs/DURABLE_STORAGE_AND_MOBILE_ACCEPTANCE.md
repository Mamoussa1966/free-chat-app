# Durable storage and mobile acceptance gate

## Durable lifecycle checkpoints

When authenticated Supabase storage is explicitly enabled, the runtime must receive an owner-scoped save acknowledgement at two boundaries:

1. After the canonical Message → Request → Round chain is validated and the Round is marked STARTED, but before provider dispatch.
2. After the Round is finalized and its accumulated results have been bound to the Request, before another Round may start.

A failed checkpoint is fail-closed: provider dispatch does not start (or the next Round is not entered), the Request is marked FAILED in the canonical runtime record, and a best-effort failed-state checkpoint is attempted. Session-only mode remains unchanged when Supabase storage is disabled.

## Storage adapter invariants

- Historical Message/Request/Round IDs and immutable bindings are append-only.
- A terminal Request.state or Round.status cannot be downgraded or changed to a different terminal value by a stale snapshot.
- The saved-history query sorts by updated_at descending with conversation_id ascending as a deterministic tie-breaker, matching the existing owner/updated_at index.

The Python adapter rejects lifecycle regressions before sending an upsert. The production PostgreSQL trigger currently enforces identity/append-only invariants but does not yet enforce lifecycle-state monotonicity server-side. That concurrency/race protection remains a separate migration gate; this PR does not apply any production DDL.

## Phone browser acceptance

The browser test launches the real main.py entrypoint locally at 390 × 844 with no Supabase Auth configuration, no provider credentials, no voice permissions, and no outbound AI requests. It checks:

- The history/clear/backup control order.
- The independent-new-chat action and its success notice.
- A visible multiline composer.
- No document/body horizontal overflow beyond the viewport.

The test does not submit a prompt, record audio, sign in, or write to Supabase. It does not replace the previously completed Auth or voice acceptance gates.
