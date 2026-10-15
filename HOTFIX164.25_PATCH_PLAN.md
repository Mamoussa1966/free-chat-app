# HOTFIX164.25 — Targeted audit correction plan
Status: IMPLEMENTATION SPECIFICATION ONLY — NOT A SOURCE REPLACEMENT OR RELEASE.
Repository: Mamoussa1966/free-chat-app
Base branch: gitops-v0.4-final

## Findings grounded in the current audit
- HOTFIX164.23 report has `target_selection_status=NO_TARGETS`, no target IDs, and zero messages/requests/rounds.
- The `main.py` read-only page intentionally runs before `_init_state()` and uses `_active_chat_without_initialization()`.
- `_active_chat_without_initialization()` returns `{}` when `st.session_state["chats"]` has no item matching `active_chat_id`.
- `HOTFIX16420_DEFAULT_TARGET_REQUEST_IDS = ("", "")`; an untouched form must not choose IDs automatically.
- The empty-target path appends `NO_EXPLICIT_TARGETS_PROVIDED`. This is expected fail-closed behavior, but it cannot establish that an existing historical conversation was audited.

## Required implementation behavior
1. Resolve an existing canonical conversation using read-only lookup only. Do not call `_init_state()`, `_active_chat()`, `_new_chat()`, hydration/rebuild functions, or provider dispatch from the forensic route.
2. If no canonical conversation can be found, emit:
   - `status: NOT_PROVEN`
   - `conversation_selection_status: NO_EXISTING_CANONICAL_CONVERSATION`
   - `blockers` includes `NO_EXISTING_CANONICAL_CONVERSATION`
   - `canonical_counts` must not be presented as proof of a valid empty history.
3. Distinguish “real existing conversation with zero records” from “no conversation found.” Neither state can pass closure.
4. In `read_only_existing_records_audit()` and `_hotfix16420_read_only_target_audit()`, empty `Message`, `Request`, and `Round` ledgers must not yield a closure-positive counter result. Return `NOT_PROVEN` for the empty-history case, while preserving `FAIL` for explicit mismatches/duplicates.
5. Never manufacture Request IDs, Messages, Rounds, Bridge evidence, provider events, or live evidence. Never auto-select latest-N requests.
6. Compare the before/after fingerprint of the exact live object and fail closed if it changes or cannot be fingerprinted.
7. Missing or incomplete strict-live Bridge evidence remains `NOT_PROVEN` or `FAIL`, never `PASS`.
8. Preserve the frozen provider identity:
   `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`

## Suggested minimal source areas
- `main.py`: `_active_chat_without_initialization`, `_render_hotfix16419_read_only_page`, `_hotfix16420_read_only_target_audit`.
- `production_platform.py`: `read_only_existing_records_audit()` (verify the exact current function name/signature before editing).
- Existing tests: `tests/test_hotfix16419_read_only_existing_records.py` and `tests/test_hotfix164_final_runtime_bridge_closure.py` (verify current paths before editing).

## Release gate
Do not label the package a final release until:
- focused regression tests pass,
- the complete repository test suite passes on the exact source tree,
- ZIP round-trip tests pass,
- manifest, workflow, artifact name, and checksums agree,
- a live read-only audit against real existing records proves the required invariants,
- strict-live Bridge closure is marked proven only when application-owned evidence actually exists.
