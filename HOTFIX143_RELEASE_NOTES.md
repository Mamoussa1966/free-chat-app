# HOTFIX143 — PROSE ISOLATION AUTHORITATIVE-GATE HARDENING

Built directly from HOTFIX142.

## Scope
- Fix the HOTFIX131 prose/runtime boundary so agent-generated audit labels cannot be mistaken for runtime control-plane fields.
- Keep REQUEST_ID, STATUS, RESULT ROW, BRIDGE_ID, and AUTHORITATIVE_RUNTIME_IDENTITY application-owned.
- Make the Security Audit authoritative over persisted request records and runtime execution events; agent prose is presentation-only.
- Add regression coverage for the three previously failing HOTFIX131 indicators and the Security Audit source-of-truth rule.

## Explicit non-goals
- No Secrets changes.
- No Models or `*_FREE_MODELS` changes.
- No Free Cascade changes.
- No Provider configuration changes.
- No Request Lifecycle changes.
- No HOTFIX141 A/B/C Harness changes.
- No Transactional Bridge architecture changes.

## Key correction
The HOTFIX142 detector could match substrings such as `REQUEST_ID` inside the audit label `AGENT_PROSE_REQUEST_ID_OVERRIDE`, causing agent-generated diagnostic prose to be interpreted as a control-plane mutation. HOTFIX143 changes the detector to require standalone control-field tokens. Structured runtime identity remains independently validated from application-owned fields.
