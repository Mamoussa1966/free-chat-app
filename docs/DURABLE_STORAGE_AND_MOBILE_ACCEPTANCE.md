# Durable storage and mobile acceptance gate

## Durable lifecycle checkpoints

When authenticated Supabase storage is explicitly enabled, the runtime must receive an owner-scoped save acknowledgement at two boundaries:

1. After the canonical Message → Request → Round chain is validated and the Round is marked STARTED, but before provider dispatch.
2. After the Round is finalized and its accumulated results have been bound to the Request, before another Round may start.

A failed checkpoint is fail-closed: provider dispatch does not start (or the next Round is not entered), the Request is marked FAILED in the canonical runtime record, and a best-effort failed-state checkpoint is attempted. Session-only mode remains unchanged when Supabase storage is disabled.

## PostgreSQL terminal-state monotonicity

Migration `20261110091030_enforce_terminal_request_round_lifecycle.sql` adds a second, narrowly scoped `BEFORE UPDATE` trigger to `public.council_conversations`.

- Once a Request reaches a terminal `state` (COMPLETED, SUCCEEDED, FAILED, REJECTED, CANCELLED/CANCELED, ABORTED, or EXPIRED), a later snapshot cannot remove the state, revert it to RUNNING, or change it to a different terminal state.
- The same rule applies to a Round's terminal `status`.
- Non-terminal → terminal transitions remain allowed; repeating the same terminal state is idempotent.
- The function uses an empty search path, schema-qualified built-ins, and no SECURITY DEFINER privilege escalation. EXECUTE is revoked from PUBLIC, anon, and authenticated; the function is reached through its trigger.
- The existing owner/RLS/identity trigger remains in place and continues to validate ownership, canonical structure, identity bindings, and append-only history.

The migration is applied to production project `wzhsilufajemyqtednie` and recorded there as version `20261110091030`. Its filename in this repository matches that recorded version.

## Database validation

- The isolated local Supabase CI stack applied the timestamped migration and ran the complete pgTAP suite: 37 tests passed.
- Production metadata confirms both the original row guard and the new terminal lifecycle guard are enabled.
- A transaction-scoped production smoke test attempted to downgrade one terminal Request and one terminal Round. Both were rejected with SQLSTATE `23514`; the canonical JSON hash was unchanged after both attempts.
- Production row totals after the smoke test were unchanged: one conversation, 32 messages, 16 Requests, and 16 Rounds.

The runtime checkpoint changes in this PR are not merged or deployed yet. Production currently has the database protection; the per-Round application checkpoints become active after the code PR is reviewed and merged.

## Phone browser acceptance

The browser test launches the real main.py entrypoint locally at 390 × 844 with no Supabase Auth configuration, no provider credentials, no voice permissions, and no outbound AI requests. It checks:

- The history/clear/backup control order.
- The independent-new-chat action and its success notice.
- A visible multiline composer.
- No document/body horizontal overflow beyond the viewport.

The automated phone-viewport test passes. Actual Android-device acceptance is still required after the reviewed application code is deployed. That manual check should not submit a prompt or call an AI provider.
