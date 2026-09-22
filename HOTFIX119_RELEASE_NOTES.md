# HOTFIX119 — DURABLE HISTORICAL LIFECYCLE BOUNDARY

Scope: V26.3 Conversation Persistence only. Provider Core, Free Cascade, Secrets, model lists, and Bridge behavior are unchanged.

## Root cause addressed
HOTFIX118 could enter a new user-message lifecycle from a narrowed current runtime object. Although the canonical commit was monotonic, the next lifecycle did not have an explicit pre-allocation boundary proving that the previously committed canonical snapshot was restored first. The historical audit also contained a fallback path to the in-memory ConversationRecord when canonical session transport was unavailable.

## HOTFIX119 changes
1. Added `load_canonical_snapshot()` as the explicit application-owned historical transport read.
2. Added `prepare_historical_runtime()` and wired it before new Message/Request ID allocation.
3. Historical audit now reads the committed canonical transport directly and fails closed with `NOT_PROVEN` when that transport is absent.
4. Rebuild remains strict replacement from the hydrated canonical snapshot.
5. Added a regression test for Message1 durable commit → runtime narrowing → preflight hydrate → Message2 append → historical audit.
6. Added a regression test that missing canonical transport cannot be replaced by current-request state.

## Required runtime proof
The deployed application must independently produce:
- HISTORICAL_MESSAGE_COUNT = 2
- HISTORICAL_REQUEST_COUNT = 2
- HISTORICAL_ROUND_COUNT = 2
- REQUEST_ID_1 != REQUEST_ID_2
- ROUND_ID_1 != ROUND_ID_2
- MESSAGE_1 → REQUEST_1 = PASS
- MESSAGE_2 → REQUEST_2 = PASS
- REQUEST_1 → ROUND_1 = PASS
- REQUEST_2 → ROUND_1 = PASS
- PREVIOUS_REQUEST_REEXECUTED = NO
- TWO_MESSAGE_ISOLATION = PASS

Local tests do not constitute proof of deployed Streamlit runtime persistence.
