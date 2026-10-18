# HOTFIX164.28 — Request-Bound Bridge Closure and Stale-Audit Invalidation

## Actual code changes

1. **One HTTP body:** provider POST transport now sends only the prepared request body bytes (`data=prepared_body`) whose SHA-256 and length were attested. It no longer also passes `json=payload`, eliminating the second serialization path that could diverge from the body attestation.
2. **Successful transport bound to application identity:** after a successful official-provider response, the runtime attestation is bound to the application Request ID, round number, executed seat/slot, executed model, and the fact that a response was attached.
3. **Strict target attestation:** STRICT_LIVE now requires request, round, target seat, transport-response, and canonical-round identity bindings. Missing, mismatched, or old attestations fail closed.
4. **Stale report invalidation:** the active read-only audit is fingerprint-bound to the current canonical conversation, history hash, request IDs, round IDs, and bridge-evidence identity fields. A cached PASS from another run is not treated as current evidence.
5. **Regression coverage:** tests cover exact HTTP body bytes, updated DeepSeek adapter expectations against the bytes actually sent, request/round mismatch rejection, correct target attestation acceptance, and stale-report invalidation.

## Preserved constraints

- `VERSION.txt` stays exactly `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`.
- No local engine, paid fallback, or dynamic model discovery is enabled.
- Read-only audit does not create requests, rounds, bridge transactions, or provider calls.
- Provider prose is never evidence of runtime execution.

## Closure state

**LIVE FINAL CLOSURE: NOT_PROVEN.** Offline tests can verify that implementation and guardrails behave as designed, but cannot prove successful live DeepSeek → Bridge commit/barrier → Gemini execution. The deployed application must generate fresh Run A and Run B evidence and pass the strict application-owned audit.
