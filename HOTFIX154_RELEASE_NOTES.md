# HOTFIX154 — V26.3/V23 CANONICAL AUDIT PREFLIGHT INVOCATION + FAIL-CLOSED EVIDENCE GATE

- Built directly on HOTFIX153; all HOTFIX153 archive entries are preserved.
- `conversation_persistence_audit()` now invokes `canonical_audit_preflight()` on the application-owned canonical path and exposes invocation/status telemetry.
- Preflight is observational: rebuilding compatibility indexes cannot erase the active request/UI projection.
- Missing canonical identity evidence is fail-closed as `NOT_PROVEN`; it cannot manufacture `PASS`.
- Continuation evidence remains fail-closed: `audit={}` => `status=NOT_PROVEN`.
- Canonical counters remain sourced only from canonical Message/Request/Round identity records; UI projection count is non-authoritative.
- Providers, explicit Free Models, Free Cascade, Secrets contract, Request→Round identity, security isolation, and provider execution are unchanged by scope.
- Regression suite: 532 passed.
