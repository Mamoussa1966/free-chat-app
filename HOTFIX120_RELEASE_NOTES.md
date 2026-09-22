# HOTFIX120 — V26.3 Canonical Conversation Store Single Contract

## Root defect fixed
HOTFIX119 exposed a split-brain condition: `v26_3_persistence` could report persisted Message/Request/Round rows while the Historical Audit independently queried `canonical_transport` and returned `CANONICAL_TRANSPORT_MISSING`.

## Contract
There is now one historical contract:

`V26_3_CANONICAL_CONVERSATION_STORE`

- append Message
- append Request
- append Round
- read historical snapshot
- HYDRATE
- REBUILD
- AUTHORITATIVE AUDIT

The session-state object is only the rerun checkpoint for this same store. The legacy `v26_3_conversation_persistence` name is retained only as a compatibility alias to the exact same underlying object; it is not an independent persistence source.

## Audit window
If a conversation contains older history, the authoritative two-message proof window is selected from the latest two application-owned USER MessageRecords and their exact Message→Request→Round mappings. No agent prose or current-request fallback is used.

## Negative contract
If no committed canonical store exists, Historical Audit remains `NOT_PROVEN` even when current runtime ledgers contain a plausible Message/Request/Round chain.

## Scope exclusions
Provider Core, Free Cascade, Secrets, model lists, and Bridge implementation were not changed.
