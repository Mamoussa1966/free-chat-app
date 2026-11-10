# Durable storage and mobile acceptance gate

## Durable lifecycle checkpoints

When authenticated Supabase storage is explicitly enabled, the runtime must receive an owner-scoped save acknowledgement at two boundaries:

1. After the canonical Message → Request → Round chain is validated and the Round is marked STARTED, but before provider dispatch.
2. After the Round is finalized and its accumulated results have been bound to the Request, before another Round may start.

A failed checkpoint is fail-closed: provider dispatch does not start (or the next Round is not entered), the Request is marked FAILED in the canonical runtime record, and a best-effort failed-state checkpoint is attempted. Session-only mode remains unchanged when Supabase storage is disabled.

## PostgreSQL terminal-state monotonicity

Migration `20261110090355_enforce_terminal_request_round_lifecycle.sql` adds a second, narrowly scoped `BEFORE UPDATE` trigger to `public.council_conversations`.

- Once a Request reaches a terminal `state` (COMPLETED, SUCCEEDED, FAILED, REJECTED, CANCELLED/CANCELED, ABORTED, or EXPIRED), a later snapshot cannot remove the state, revert it to RUNNING, or change it to a different terminal state.
- The same rule applies to a Round's terminal `status`.
- Non-terminal → terminal transitions remain allowed; repeating the same terminal state is idempotent.
- The function uses an empty search path, schema-qualified built-ins, and no SECURITY DEFINER privilege escalation. EXECUTE is revoked from PUBLIC, anon, and authenticated; the function is reached only through its trigger.
- The existing owner/RLS/identity trigger remains in place and continues to validate ownership, canonical structure, identity bindings, and append-only history.

The Python adapter has the matching early guard, but the PostgreSQL trigger is the authoritative concurrency boundary: concurrent UPDATEs serialize on the row, and the trigger evaluates the current OLD row before accepting the new snapshot.

## PostgreSQL acceptance tests

The local pgTAP suite adds cases for:

- A valid RUNNING/STARTED → COMPLETED/COMPLETED transition.
- An idempotent save of the same terminal states.
- Rejecting a terminal Request downgrade and a change to a different terminal state.
- Rejecting the equivalent two Round mutations.

The migration is applied only by the local Supabase CI stack in this PR. It has not been applied to the production project. Production application remains a separately approved deployment step.

## Phone browser acceptance

The browser test launches the real main.py entrypoint locally at 390 × 844 with no Supabase Auth configuration, no provider credentials, no voice permissions, and no outbound AI requests. It checks:

- The history/clear/backup control order.
- The independent-new-chat action and its success notice.
- A visible multiline composer.
- No document/body horizontal overflow beyond the viewport.

The test does not submit a prompt, record audio, sign in, or write to Supabase. It does not replace hands-on acceptance on the actual Android device.
