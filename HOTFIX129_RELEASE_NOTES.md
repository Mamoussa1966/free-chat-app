# HOTFIX129 — TWO-REAL-TURN PERSISTENCE EXECUTION GATE

Built directly from HOTFIX128 without deleting any existing packaged file.

## Root cause addressed
HOTFIX128 correctly fixed the contract to `REQUEST_2 → ROUND_2`, but a one-submission prompt that *described* two messages cannot create two runtime Requests. The observed state (`2 persisted messages / 1 request / 1 round`) is therefore correctly `NOT_PROVEN`.

HOTFIX129 makes this distinction explicit and adds a regression test that executes two independent runtime submissions in the same conversation, including a simulated narrowed-runtime/Streamlit-rerun boundary between them.

## Scope
- Preserve the existing Provider Core, Free Cascade, Secrets, Model Lists and Bridge behavior.
- Preserve canonical ConversationRecord as the sole historical authority.
- Preserve fail-closed identity semantics.
- Require the second Request/second Round to be created by a second real user submission.
- Restore the full canonical history before allocating the next Request.
- Derive the next Round ordinal from the canonical history.
- Add regression coverage for the exact two-turn lifecycle and for the one-turn non-fabrication case.

## Acceptance
A release is accepted only after:
1. full pytest passes in the source tree;
2. the exact ZIP is re-extracted;
3. full pytest passes again from the re-extracted ZIP;
4. all HOTFIX128/HOTFIX127 members remain present;
5. the active HOTFIX129 contract contains `REQUEST_2 → ROUND_2` as the only positive second-round mapping;
6. the active test rejects a one-submission attempt as `NOT_PROVEN`;
7. the runtime test proves two separate submissions yield exactly two canonical Messages, Requests and Rounds.
