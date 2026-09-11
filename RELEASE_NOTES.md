# V22.1-FINAL-EXACT-NAMES-UPDATED-HARDENED-HOTFIX14

- Preserves the complete prior project and regression suite.
- Keeps the strict Free-only contract: no Local Engine, no paid fallback, and no implicit model selection.
- Keeps authoritative executed_model identity and ordered Free Cascade behavior.
- Adds durable request/history identity: every new request receives a unique request_id and monotonically increasing Request number.
- Displays Request N · Round M in AI rooms so separate requests with the same round number cannot be mistaken for duplicate execution.
- Enforces (request_id, round, seat) uniqueness against the entire retained chat history, not only a local per-run seen set.
- Keeps idempotency fingerprinting separate from request identity.
- Preserves last_results as the latest request result set while History retains request-scoped identities.
- Release is validated with syntax checks, the full test suite, ZIP integrity checks, and stale-version detection.
