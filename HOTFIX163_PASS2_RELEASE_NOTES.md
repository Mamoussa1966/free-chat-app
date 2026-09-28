# HOTFIX163 Pass 2 — Final Regression Closure Candidate

This package is rebuilt from the latest HOTFIX163 artifact available in the
ChatGPT Library/runtime and preserves its complete extracted file tree.

Production hardening in this pass:
- Bridge forbidden-value redaction is enforced across BOTH `user_prompt` and
  `shared_context` before construction of the provider HTTP prompt.
- No test assertions were modified.
- No tests were disabled, xfailed, or removed.
- No Local Engine / paid fallback / implicit model selection was introduced.

Verification performed on this package:
- `pytest -q` against the available packaged test tree: PASS.
- This packaged tree contains 551 collected tests; it is NOT the 561-test
  workspace reported by the user's current run.

Therefore this artifact is intentionally marked CANDIDATE, not FINAL VERIFIED.
The user's 561-test workspace must remain the authoritative acceptance gate:
`FAILED = 0` on the original tree, followed by ZIP round-trip extraction and
`FAILED = 0` again from the extracted tree.
