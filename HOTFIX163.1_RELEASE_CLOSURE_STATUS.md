# HOTFIX163.1 — Final Regression Closure Status

Base: HOTFIX161/162-compatible working tree from the supplied ZIP.

## Runtime/code fixes applied
- Restored required `.streamlit/secrets.toml.example` path without deleting the historical `streamlit./secrets.toml.example` artifact.
- Enforced provider-boundary bridge redaction marker `[REDACTED_BRIDGE_VALUE]`.
- Extended HOTFIX135 multi-request isolation to inspect persisted execution events and exposed both required regression check keys.
- Made missing second Request a regression `FAIL`, not `NOT_PROVEN`, when the application-owned request collection exists.
- Materialized canonical Message/Request identity at the explicit lifecycle write boundary in `message_ledger.record_message`; audits remain read-only.
- Made message relinking update the existing application-owned ledger row rather than silently retaining an empty `round_id`.
- Made `begin_round` honor the Request's already-persisted `canonical_round_base`, preventing Request 2 from becoming Round 1.
- Made canonical hydration materialize `canonical_runtime_indexes` from canonical identity records.

## Verification
Full suite on the working tree:

578 passed, 1 failed.

The remaining failure is:
`tests/test_hotfix117_bridge_prompt_boundary.py::test_hotfix117_preserves_hotfix116_request_determinism_contract`

The failure is an internal test-contract contradiction with `tests/test_hotfix111_release_contract.py`:
- HOTFIX111 requires `VERSION.txt == V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`.
- HOTFIX117 requires the same `VERSION.txt` to equal `V22.1-HOTFIX117-PRODUCTION-HARDENED`.

Both assertions read the same physical file. No single file content can satisfy both simultaneously. Tests were not modified.

Therefore this artifact is a **CANDIDATE**, not a final closure release. `FAILED=0` has not been claimed.
