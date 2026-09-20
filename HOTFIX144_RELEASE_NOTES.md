# HOTFIX144 — PROSE/RUNTIME TRUTH SEPARATION + AUTHORITATIVE AUDIT GATE

Base: HOTFIX143, preserved intact except for the authoritative prose/runtime audit layer and regression tests.

## Scope
- Authoritative Request/Result/Execution identity is derived only from application-owned structured runtime records.
- The HOTFIX131 audit is scoped to the current Request ID before evaluating identity.
- A/B/C combined UI result sets cannot cross-contaminate the current Request audit.
- Agent prose is presentation-only: fake Request IDs, statuses, result rows, bridge IDs, and counters cannot overwrite or fail authoritative identity checks merely by appearing in prose.
- A real mismatch in application-owned structured records still fails the gate.
- Security audit uses persisted runtime records, never agent message text, for the authoritative gate.
- No Secrets, Models, *_FREE_MODELS, Cascade ordering, Request Lifecycle, A/B/C Harness, or Transactional Bridge core policy changes.

## Explicit non-scope
Bridge C `WRITE = FAIL` versus `PRODUCTION_GATE = PASS` is intentionally not changed by HOTFIX144. It remains a separate bridge-consistency issue and must not be represented as a fully successful bridge proof.
