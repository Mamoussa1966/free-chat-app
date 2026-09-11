# V22.1-FINAL-EXACT-NAMES-UPDATED-HARDENED-HOTFIX14

- Preserves the complete prior source and test suite.
- Adds/retains cascade invariants: candidate #1 success stops; retryable #1 failure may advance to #2, and #2 success stops before #3.
- Execution identity is carried as `executed_model` and must match the successful model and final attempted candidate.
- Release consistency is checked so stale HOTFIX version markers cannot ship.
