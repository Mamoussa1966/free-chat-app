# HOTFIX121 — V26_3_CANONICAL_CONVERSATION_STORE SINGLE SOURCE OF TRUTH

## Scope
HOTFIX121 repairs HOTFIX120 itself. `V26_3_CANONICAL_CONVERSATION_STORE` is the only historical Message/Request/Round source of truth.

- `conversation_store.py` owns the canonical record and snapshot reader.
- `conversation_persistence_v26.py` is a compatibility interface over that same store; it does not maintain or read a second historical bucket.
- Historical Audit reads the same canonical snapshot, then validates the selected two-message chain.
- Runtime compatibility indexes are rebuild-only caches and never historical authority.
- Uncommitted/current runtime records cannot become historical proof.
- Agent prose is never used for identity, counters, or historical status.
- Provider Core, Free Cascade, Secrets, Model Lists, and Bridge behavior are outside this fix.

## Historical proof contract
The audit selects the latest two application-owned USER MessageRecords from the canonical snapshot and requires:

`HISTORICAL_MESSAGE_COUNT=2`
`HISTORICAL_REQUEST_COUNT=2`
`HISTORICAL_ROUND_COUNT=2`
`MESSAGE_1→REQUEST_1=PASS`
`MESSAGE_2→REQUEST_2=PASS`
`REQUEST_1→ROUND_1=PASS`
`REQUEST_2→ROUND_1=PASS`
`ROUND_ID_1 != ROUND_ID_2`
`PREVIOUS_REQUEST_REEXECUTED=NO`
`TWO_MESSAGE_ISOLATION=PASS`

If the canonical snapshot is unavailable, the result remains `NOT_PROVEN` and no current-request fallback is allowed.

## Validation
- HOTFIX120 base ZIP inspected directly.
- 13 focused canonical lifecycle/store tests passed.
- `python -m compileall -q .` passed.
- ZIP integrity verified.
- Original HOTFIX120 files preserved; no original file deleted.
