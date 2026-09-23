# HOTFIX126 — AUTHORITATIVE ROUND IDENTITY / FINAL PERSISTENCE GATE

Bridge-only behavior from HOTFIX125 is preserved. HOTFIX126 adds the missing
proof boundary for historical Round identity.

## Core correction

The runtime no longer treats an audit label such as `ROUND_ID_2` as proof that
the second historical Round is actually Round 2.

For every newly-created canonical RoundRecord, the runtime persists:

- `round`: the conversation-scoped numeric Round ordinal
- `round_id`: an ID whose `:rN` suffix must match that ordinal
- `round_identity_contract`: `V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1`

The next Request starts from the highest numeric Round already committed in the
Application-Owned canonical ConversationRecord. Therefore, with one round per
Request:

`Request 1 -> Round 1`
`Request 2 -> Round 2`

This is derived from the canonical ledger, not Agent Prose, UI labels, or the
current/narrow Request ledger.

## Production regression gate

When the HOTFIX126 round-identity contract is present, Production readiness
requires all of the following:

1. Every canonical RoundRecord has a positive numeric ordinal.
2. `round` equals the numeric suffix of `round_id`.
3. Round IDs are unique.
4. Round ordinals are unique.
5. The canonical ordinal sequence is exactly `1..N`.
6. The application-owned historical audit proves `Round 1` and `Round 2` from
   the ledger itself for the two-message persistence test.
7. A malformed `Round 2` label backed by `round_id ...:r1` fails the gate.

No audit-only relabeling can satisfy this gate.

## Bridge contract preserved

HOTFIX125 remains unchanged:

- Bridge Test Not Requested -> `NOT_REQUESTED`; no Bridge FAIL is created.
- Bridge Test Requested -> all ten Bridge checks are mandatory.
- Any missing, `NOT_PROVEN`, or failed Bridge condition prevents Production PASS.

## Provider contract preserved

- Frozen Provider Core remains `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`.
- No Local Engine.
- No Paid fallback.
- No automatic model selection.
- No Secrets or `*_FREE_MODELS` changes.
- Existing HOTFIX125 ZIP members are preserved; this release only adds the
  HOTFIX126 regression/gate artifacts and modifies the Round-identity runtime.
