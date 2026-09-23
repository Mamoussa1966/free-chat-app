# HOTFIX146 — V23 FINAL CLOSURE AUDIT CONTRACT

## Purpose

Add an observational V23 Final Closure Audit above the frozen provider core and
HOTFIX130 persistence layer. The audit does not mutate canonical persistence,
provider execution, model selection, Free Cascade, or Bridge behavior.

## Required separation

1. `REQUEST_CREATED` means a unique application-owned canonical RequestRecord exists.
2. `EXECUTION_STARTED` means a persisted runtime execution event has
   `execution_started == true`.
3. `NOT_EXECUTED` means an explicit persisted runtime classification is exactly
   `NOT_EXECUTED`; absence of an execution event is not silently converted to it.
4. UI/result rows are presentation projections only.
5. UI message count is never an authoritative canonical message counter.
6. Security FAIL must expose the exact failed application-owned checks.
7. Missing authoritative evidence remains `NOT_PROVEN` rather than PASS.

## Preservation

- HOTFIX123.2 provider core preserved.
- HOTFIX129 Message→Request→Round contract preserved.
- HOTFIX130 canonical counter semantics preserved.
- No change to `conversation_persistence_v26.py`.
- No change to `conversation_store.py`.
- No change to `conversation_v25_runtime.py`.
- No provider/model/cascade contract changes.

## Closure rule

The audit can report PASS only when canonical evidence is present, persistence
counter semantics remain consistent, and the freshly executed security audit is
PASS. A stale UI label or agent prose cannot satisfy any gate.
