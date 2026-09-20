# HOTFIX142 — PROSE ISOLATION HARDENING

Built directly from HOTFIX141.

## Scope
- Fix only the HOTFIX131 Agent Prose Isolation boundary.
- Suppress control-plane metadata embedded inside inline/table/JSON-like provider prose, not only metadata at the beginning of a line.
- Harden the runtime prose audit to detect the same inline control-plane patterns.
- Preserve application-owned Request IDs, Bridge IDs, lifecycle accounting, Free Cascade behavior, provider execution, Bridge implementation, Secrets, model lists, provider configuration, Local Engine policy, Paid fallback policy, and Automatic Model Selection policy unchanged.

## Non-goals
- No Secrets changes.
- No model-list changes.
- No Cascade ordering changes.
- No Request Lifecycle changes.
- No Transactional Bridge changes.
- No provider configuration changes.
- No new API or fallback mechanism.

## Verification
- Existing HOTFIX141 test suite retained.
- Added focused HOTFIX142 regression tests for inline/table control metadata and authoritative identity preservation.
