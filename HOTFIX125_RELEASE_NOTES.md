# HOTFIX125.1 — REQUEST CONTINUATION + BRIDGE ISOLATION REGRESSION FIX

Applied strictly on top of HOTFIX125.

- Explicit continuation markers resolve to the existing authoritative Request ID.
- Continuation never allocates a new Request ID, round, provider execution, or Bridge.
- Completed Request results and synthesis are reused from the persisted application-owned request record.
- Existing HOTFIX123.2 single-request, seat+round, cascade, and bridge controls are preserved.
- No Secrets or model lists are changed.
- Full V23 audit remains runtime-derived and does not treat NOT_RUN as PASS.

Regression target: HOTFIX125 continuation previously generated a second Request ID and a second Bridge audit, producing false bridge isolation failures.
