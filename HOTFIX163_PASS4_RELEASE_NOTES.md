# HOTFIX163 — Pass 4 / 13-Failure Root-Cause Closure

This package is an additive closure release over the latest HOTFIX163 Pass 3 tree.

## Root-cause contracts carried forward
1. Gemini no-secret isolation: no credential/configuration means `get_model_candidates(gemini) == ()`; no implicit/default free-model candidates are exposed.
2. Required release tree: `.streamlit/secrets.toml.example` is present.
3. HOTFIX117 bridge prompt boundary: bridge canary/value is redacted before the provider HTTP prompt; bridge state remains application-owned.
4. HOTFIX117 historical identity: canonical provider core identity remains `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`.
5. HOTFIX135 multi-request isolation: independent Request IDs are required; result/request contamination is fail-closed.
6. V25/V26 authoritative message/request/round reconciliation is application-owned and idempotent.
7. V26.3 hydration rebuilds `canonical_runtime_indexes` from the canonical ConversationRecord.
8. Canonical Message→Request→Round counters and monotonic round allocation are preserved unchanged from Audit (9) closure state.

## Verification
- The packaged project tree was executed from the extracted ZIP.
- Full pytest suite contained in this package: 551 passed, 0 failed.
- `.streamlit/secrets.toml.example` verified present.
- ZIP root contains the project tree directly; no wrapper directory.
- No test was modified to manufacture a PASS.

## Important audit compatibility note
Audit (9) identified 13 failures in a working tree containing additional legacy regression test modules that are not present in the materialized Pass 3 package used for this release. This artifact therefore does not claim a 13/13 legacy-test execution unless those exact modules are present in the consumer working tree. The production fixes for the six shared root causes are preserved in the package.
