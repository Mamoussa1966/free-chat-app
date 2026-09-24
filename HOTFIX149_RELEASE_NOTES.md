# HOTFIX149 — V26.3 LIVE CANONICAL COUNTER RUNTIME CLOSURE

## Purpose
Close the remaining verification gap after HOTFIX148 without changing provider behavior or creating another counter implementation.

## Contract
The authoritative V26.3 counters MUST be derived from the application-owned Canonical ConversationRecord identity collections:
- `messages`: identity-bearing `role=user` MessageRecords only
- `requests`: identity-bearing RequestRecords only
- `rounds`: identity-bearing RoundRecords only

UI projections, rendered message lists, assistant/provider/synthesis/system artifacts, current-request ledgers, and model prose are not counter authorities.

## Runtime proof added
`tests/test_hotfix149_v26_3_live_canonical_counter_runtime.py` executes the production runtime functions, not a copy of the counter algorithm:
- `canonical_create_lifecycle`
- `commit_canonical_record`
- `load_canonical_snapshot`
- `hydrate_canonical_record`
- `rebuild_runtime_indexes_from_canonical`
- `authoritative_audit`
- `persistence_audit`

The tests deliberately inject non-user artifacts into the canonical store and a larger/noisy UI projection, then require the authoritative and persistence counters to remain exactly 2/2/2.

A second test simulates a Streamlit rerun that narrows the in-memory projection to one turn. Hydration must restore the committed canonical record and the authoritative counters must remain 2/2/2.

## Non-regression
No provider adapters, credentials, explicit `*_FREE_MODELS`, endpoints, cascade order, Local Engine, Paid fallback, automatic model selection, Request ID contract, Round identity contract, or Bridge protocol are changed.

## Preservation
Built additively from the complete HOTFIX148 package. No existing packaged file is deleted.
