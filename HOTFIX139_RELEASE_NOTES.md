# HOTFIX139 — Fresh Request + Bridge Security Isolation

Built directly from HOTFIX138.

## Fixes
- Continuation detection is now line-scoped to an explicit first-line control prefix.
- Arbitrary regression prose containing words such as `continuation`, `no new request`, `Request A/B/C`, or `BRIDGE` cannot switch a fresh submission into continuation mode.
- Existing explicit continuation controls remain supported when a persisted Request ID is supplied.
- Bridge audit receives the control-free/sanitized user input after application-owned bridge control extraction, so a bridge assignment used as test control is not misreported as a user-prompt leak.
- Provider-layer isolation remains fail-closed and is still checked against the actual provider input/runtime payload.
- No changes to Secrets, provider model lists, Free Cascade policy, Local Engine policy, or Paid fallback policy.

## Validation
- Full regression suite: 395 passed.
- Python compileall: PASS.
- Packaged ZIP integrity: PASS.
