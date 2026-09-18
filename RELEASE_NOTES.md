# HOTFIX117 — TRANSACTIONAL BRIDGE READ / PROMPT BOUNDARY ISOLATION

V22.1-HOTFIX117-PRODUCTION-HARDENED

## Scope
Built directly from the complete HOTFIX117 release artifact. HOTFIX117 request determinism is preserved. This hotfix addresses only the Bridge Read → provider-prompt boundary exposed by the runtime audit.

## Fix
- Adds a final, application-supplied bridge-value redaction guard inside `call_seat()` immediately before the official HTTP request is constructed/sent.
- The guard operates on the fully assembled provider prompt, covering both current user text and Shared Context.
- The target provider receives only the sanitized bridge availability/context representation.
- `BRIDGE_RESULT` values remain in application-owned Transactional Bridge State and are resolved only after `COMMIT → BARRIER → READ`.
- No second provider request is introduced by READ resolution.
- HOTFIX117 duplicate-request / request-determinism controls remain intact.
- Secrets and `*_FREE_MODELS` are untouched.

## Required gate
The prior release is not a Production Gate for the bridge isolation test because its runtime audit reported `GEMINI_INPUT_PROMPT_CONTAINS_VALUE = YES`. HOTFIX117 must rerun the same bridge isolation test and require:

`WRITE → VALIDATE → COMMIT → BARRIER → READ`

with `GEMINI_INPUT_PROMPT_CONTAINS_VALUE = NO`, `BRIDGE_STATE_CONTAINS_VALUE = YES`, and `MATCH = PASS`.
