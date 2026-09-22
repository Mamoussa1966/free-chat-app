# HOTFIX116 — AUTHORITATIVE CANONICAL REQUEST→ROUND→MESSAGE CHAIN

## Scope
Fix the V26.3 Historical Persistence defect without adding a second audit layer and without changing Provider Core, Free Cascade, Secrets, Model Lists, or Bridge behavior.

## Defect fixed
The authoritative audit could see the current/narrow ConversationRecord while the complete application-owned canonical history existed in the persistence transport. Request 1 could therefore disappear from the authoritative historical view after the Message 2 rerun.

## Lifecycle contract
Request 1 → Round 1-A → Message 1
Request 2 → Round 1-B → Message 2
→ canonical ConversationRecord
→ HYDRATE
→ REBUILD INDEXES
→ existing AUTHORITATIVE AUDIT

## Changes
1. Canonical hydration restores the committed canonical ConversationRecord as the authoritative runtime snapshot instead of merging a narrowed current record over it.
2. The authoritative audit rebinds to the existing canonical persistence bucket when the direct ConversationRecord alias is absent; it does not use current request ledgers or agent prose as historical fallback.
3. The existing audit now exposes explicit Request→Round-1 mapping fields and verifies the canonical transport counts before declaring PASS.
4. `_run_council()` passes `st.session_state` into the real `begin_round()` lifecycle so the round creation boundary uses the same canonical transport.
5. No provider/cascade/secret/model-list/bridge logic was changed.

## Required runtime proof
PASS requires the existing authoritative audit to contain:
- HISTORICAL_MESSAGE_COUNT = 2
- HISTORICAL_REQUEST_COUNT = 2
- HISTORICAL_ROUND_COUNT = 2
- MESSAGE_1 → REQUEST_1 = PASS
- MESSAGE_2 → REQUEST_2 = PASS
- REQUEST_1 → ROUND_1 = PASS
- REQUEST_2 → ROUND_1 = PASS
- ROUND_IDS_UNIQUE = PASS
- PREVIOUS_REQUEST_REEXECUTED = NO
- TWO_MESSAGE_ISOLATION = PASS
- HISTORICAL_SOURCE = V26_3_CONVERSATION_PERSISTENCE
- AUTHORITATIVE_SOURCE = APPLICATION_OWNED_RUNTIME_STATE

No ID or counter is accepted from provider/agent prose.
