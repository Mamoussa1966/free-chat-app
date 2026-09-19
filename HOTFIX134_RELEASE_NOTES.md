# HOTFIX134 — AUTHORITATIVE IDENTITY / PROSE AUDIT COMPLETION

Base: `HOTFIX133_FINAL.zip`
Core identity preserved: `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`

## Scope
Narrow follow-up after the HOTFIX131 production regression run. No Secrets, provider model lists, Free Cascade order, API routing, or Bridge execution contract changes.

## Fixes
1. Adds an application-owned HOTFIX131 runtime audit for:
   - `AGENT_PROSE_REQUEST_ID_OVERRIDE`
   - `AGENT_PROSE_STATUS_OVERRIDE`
   - `AGENT_PROSE_RESULT_ROW_INJECTION`
   - `AUTHORITATIVE_RUNTIME_IDENTITY`
2. The audit validates structured request/event identity against the runtime Request ID and never treats provider prose as an authority.
3. Explicitly exposes Bridge control-record redaction and prose/control leakage state in the UI.
4. Keeps application-owned Bridge values redacted; `[REDACTED]` is never treated as an actual bridge value.
5. Preserves HOTFIX132 Dispatch Gate and HOTFIX133 cascade-accounting behavior.
6. Keeps the complete file tree and all prior regression tests.

## Expected runtime evidence
A valid HOTFIX131 regression run must show the explicit identity/prose audit fields. No PASS is inferred merely from agent-generated text.
