# HOTFIX164.26 — Canonical Bridge Evidence Rehydration

## Purpose

The outstanding failure was not that the regression suite established a live Bridge transaction. It was that strict-live closure auditing depended on the volatile `chat["bridge_runtime_evidence_store"]` cache after the completed request had already committed its Bridge evidence to the V26.3 canonical RequestRecord. On a Streamlit rerun, that cache can be absent even while the canonical request row remains persisted.

This change makes the canonical RequestRecord the authority for `STRICT_LIVE` Bridge evidence. The audit and sanitized export recover the evidence stored as `request_record["bridge_runtime_evidence"]`, verify its Request ID and canonical Round ID, and reject sidecar-only evidence. If the sidecar conflicts with the canonical copy, proof fails closed. This does not allocate requests, rounds, bridges, or provider work during an audit.

## Preserved contracts

- Frozen provider identity remains `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`; `VERSION.txt` is unchanged.
- Provider policy remains official API only, explicit free-model allowlists, no Local Engine, no paid fallback, and no dynamic model discovery.
- The audit report remains `hotfix164.23-explicit-target-read-only-forensics/v1`; this release does not change its wire schema.
- Provider-result prose is not used as Bridge runtime authority; the raw bridge value and HTTP body are not exported.
- Missing/incomplete canonical evidence remains `NOT_PROVEN`.

## Validation boundary

Regression tests for canonical evidence recovery, sidecar loss, sidecar-only rejection, and sidecar/canonical conflict are software regression tests. They are not provider executions. The release package does **not** claim live final closure. Live closure remains `NOT_PROVEN` until the deployed application records two real, request-bound DeepSeek Seat 7 → Gemini Seat 2 transactions with complete application-owned WRITE → VALIDATE → COMMIT → BARRIER → TARGET_DISPATCH → TARGET_RESPONSE → READ → MATCH evidence, prepared HTTP payload attestation, prompt/payload isolation, and canonical Message→Request→Round bindings.

## Deployment note

This is a local release candidate only until its files are committed and the matching CI workflow succeeds on the deployment branch. After deployment, send the two Bridge test messages in the same canonical conversation and run the read-only explicit-target audit against those exact Request IDs. Do not use synthetic fixtures or a blank-target audit as proof of live closure.
