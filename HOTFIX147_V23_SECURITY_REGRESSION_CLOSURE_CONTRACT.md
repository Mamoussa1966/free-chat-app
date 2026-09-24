# HOTFIX147 Contract

HOTFIX147 is restricted to three closure defects identified by V23 Final Closure Audit:

1. Security audit false positive caused by searching serialized chat text for the literal token `raw_provider_payload`.
2. Regression test/API mismatch for `_authoritative_ui_projection` and `_format_authoritative_counter_summary`.
3. Explicit separation of UI projection counters from canonical Message/Request/Round counters.

The canonical persistence implementation is not modified by this release.

### Security rule
A security failure requires an actual non-empty forbidden application-owned field or a credential pattern; prose labels and user prompt text are not evidence.

### Counter rule
`chat["messages"]` is a presentation projection and is never authoritative. Canonical Message/Request/Round counts are derived from identity-bearing records in the application-owned canonical store.

### Fail-closed rule
Missing or contradictory application-owned evidence remains `NOT_PROVEN`/`FAIL`; no agent prose or UI label can promote it to PASS.
