# HOTFIX113 — Cascade Execution Identity Hardening

Version: `V22.1-HOTFIX113-PRODUCTION-HARDENED`

Built directly from the verified HOTFIX113 release artifact while preserving the complete file tree and existing tests.

## Fixes
- Makes `cascade_position` authoritative from the actual `attempted_models` execution ledger.
- Uses one-based Free Cascade numbering: first actual API attempt = #1.
- Persists `cascade_position` with each successful history message.
- Renders the executed Free Cascade number separately from the configured Free #1 catalog entry.
- Removes the previous UI ambiguity where a successful #3 execution could still be displayed as `Free #1`.
- Adds regression tests proving a three-attempt execution reports `cascade_position = 3` and preserves that identity in history.
- No Secret, `*_FREE_MODELS`, provider catalog, Local Engine, or Paid fallback behavior is changed.

## Preservation
- HOTFIX113 transactional bridge isolation remains unchanged.
- Prompt non-leak protections remain unchanged.
- Existing test tree is preserved.
