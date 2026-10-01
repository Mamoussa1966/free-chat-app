# HOTFIX163.1 — Canonical Read-Only Diagnostic Boundary Closure

Incremental patch over HOTFIX163.1 repository baseline. Existing project files are preserved.

## Fix
- Expanded the HOTFIX163.1 local diagnostic gate from the original three read-only variants to the complete repository/artifact acceptance namespace used by the closure workflow:
  - Repository Canonical State Boundary
  - Clean Two-Record Canonical Fixture
  - Read Path Side-Effect Isolation
  - Version Contract
  - Full Regression Test
  - V26.3 Canonical Persistence Test
  - Gemini No-Secret Isolation Test
  - HOTFIX117 Bridge Prompt Boundary Regression
  - Audit / Read / Hydration Side-Effect Regression
  - ZIP Round-Trip Acceptance Test
- The message composer no longer auto-detects or blocks prompts merely because they start with HOTFIX163.1. This restores normal chat input/submission for closure test text and ordinary user messages.
- The repository canonical diagnostic remains available only through an explicit sidebar control, so local read-only auditing cannot silently hijack a user message or create a Request/Round/provider execution.
- No provider, cascade, synthesis, canonical store, or test was modified to manufacture a passing result.

## Verification
- Full pytest executed from the packaged project root: 579 passed, 0 failed, 0 errors.
- The packaged artifact is re-extracted into a fresh directory and the full suite is executed again before release.
- VERSION.txt remains the canonical V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE value.
