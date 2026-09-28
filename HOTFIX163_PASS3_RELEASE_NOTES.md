# HOTFIX163 Pass 3 — Regression Closure

This release is an additive production/runtime closure over HOTFIX163 Pass 2.

## Production changes
- Canonical hydration now remains deterministic when Session-State transport is unavailable: an already committed canonical ConversationRecord is the only fallback source.
- V26 message-ledger reconciliation preserves the first application-owned Message→Request identity and marks contradictory bindings without overwriting the authoritative binding. Reconciliation remains idempotent.
- No provider prose, UI projection, completion order, or generated identity is used as a canonical fallback.

## Regression contract
- Message identity is fail-closed when application-owned identity is missing.
- Gemini model candidates remain strictly explicit `GEMINI_FREE_MODELS`; no implicit/default model is introduced by missing Secrets.
- Existing release tree and tests are preserved; no test is modified to manufacture a PASS.
- Bridge value/key remains outside final provider prompts.
- Request/round identity remains request-scoped and canonical.

## Verification performed
- Full pytest on this extracted Pass 3 tree: PASS before packaging.
- ZIP root contains the project tree directly (no wrapper directory).
