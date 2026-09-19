# HOTFIX131 — AUTHORITATIVE RESULT / IDENTITY / BRIDGE-PROSE ISOLATION

- Provider prose is untrusted presentation data and cannot define Request ID, status, classification, model, attempt, cascade action, or result rows.
- Structured result identity remains application/lifecycle-owned.
- Agent-generated Request ID/control metadata is suppressed from visible prose.
- Bridge values and BRIDGE_RESULT control records are suppressed at the agent-prose boundary.
- No Secrets, model catalogs, cascade controller, Bridge implementation, Request Lifecycle, or runtime accounting changes.
- Preserves the complete HOTFIX129 source ZIP file set.
