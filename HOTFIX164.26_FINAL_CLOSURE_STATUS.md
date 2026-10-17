# HOTFIX164.26 — Final Closure Status

**Status: NOT_PROVEN — live Bridge closure has not been established by this package.**

## Defect addressed

The strict-live audit was reading `bridge_runtime_evidence_store`, an in-memory sidecar that may be empty after a Streamlit rerun, while the completed request persisted its application-owned Bridge record on the canonical V26.3 RequestRecord. The audit and sanitized snapshot export now recover strict-live evidence from that canonical request field, check that it belongs to the exact Request ID and canonical Round ID, and reject sidecar-only or conflicting evidence.

## What the release tests establish

The regression suite checks the evidence-rehydration code path, its fail-closed behavior when canonical evidence is missing, rejection of sidecar-only evidence for strict-live requests, sidecar/canonical conflict handling, canonical evidence export, the frozen provider identity, and the full archive round-trip. Those software tests do **not** establish that a live provider API call occurred.

## Acceptance criteria for live final closure

The deployed application must contain two real explicit target requests from the same canonical conversation. For each request, the canonical Message→Request→Round chain must match the app-owned evidence for a DeepSeek Seat 7 source execution and a Gemini Seat 2 target execution. The evidence must prove the ordered phases `SOURCE_EXECUTION → WRITE → VALIDATE → COMMIT → BARRIER → TARGET_DISPATCH → TARGET_RESPONSE → READ → MATCH`, a committed terminal state, a real prepared-request HTTP payload attestation and matching payload hash, and no Bridge value, Bridge key, Bridge ID, Request ID, or canonical Round ID leaking into prohibited user/provider prompts or the Gemini HTTP payload. Two distinct request-bound Bridge hashes must be present. Missing or incomplete evidence remains `NOT_PROVEN`.

## Deployment boundary

This candidate was prepared locally for download. It has not been committed or pushed to GitHub by this package workflow. The user must apply the replacement files and wait for the repository workflow to complete before the patched source is deployed. After deployment, send the two test messages in the app and run the read-only explicit-target audit with those two actual Request IDs. Do not infer live closure from build success, fixtures, blank-target audits, model prose, or a ZIP hash.
