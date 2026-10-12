# HOTFIX164.17 — Per-Request Bridge Runtime Proof Closure

## Scope
This release narrows the remaining Bridge proof gap without rewriting V26.3 canonical identity allocation, Message → Request → Round binding, or authoritative counters. It builds on HOTFIX164.16 and preserves the frozen provider-core release identity.

## Changes
- Stop inferring an unknown `target_seat=0` as Gemini Seat 2 in compatibility traces. In strict live execution, the target identity must be bound by an observed COMMIT event against the configured Gemini Seat 2 object.
- Validate the complete application-owned runtime sequence, per-event Request ID and Round binding, source identity (DeepSeek Seat 7), and every target-side identity (Gemini Seat 2, including COMMIT, BARRIER, dispatch, response, and READ; Application for MATCH).
- Reject a strict READ when the target object is not Gemini Seat 2.
- Include payload attestation metadata in the per-Request proof record: SHA-256 digest, hash-integrity status, prepared-request verification, and the actual HTTP transport boundary. The raw HTTP body is not exported.
- Add a separate sanitized `bridge_runtime_evidence_export` with one record for each requested/stored Request. It binds each record to its canonical Round, reports missing evidence as `NOT_PROVEN`, reports contradictory target/sequence evidence as `FAIL`, and proves Bridge-hash uniqueness only when multiple distinct records exist.
- Preserve the safe legacy `bridge_runtime_evidence_store` projection for backwards compatibility, while ensuring the newly added export does not include raw Bridge IDs, raw Bridge values, or HTTP request bodies.

## Preserved invariants
- `VERSION.txt` remains `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`.
- V26.3 identity allocation and canonical message/request/round counter logic are not changed.
- No Local Engine, paid fallback, or dynamic model discovery is introduced.
- Agent prose is not an authoritative source for counters or Bridge lifecycle proof.

## Acceptance boundary
`pytest -q`, release-validator, ZIP extraction, and extracted-copy tests must pass on the exact candidate artifact. This local/source-level package does not claim a live two-message Streamlit Bridge closure unless the deployed runtime produces complete, independent application-owned evidence for both Requests.
