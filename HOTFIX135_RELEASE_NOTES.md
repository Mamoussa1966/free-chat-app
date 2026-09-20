# HOTFIX135 — V23 PRODUCTION REGRESSION / MULTI-REQUEST ISOLATION

Built directly from HOTFIX134. This release adds an application-owned regression audit for multiple independent Requests.

## Guarantees checked
- At least two independent persisted Requests are required before PASS.
- Unique Request IDs across the selected Request records.
- Every persisted result, result key, execution claim and runtime execution event remains scoped to its owning Request ID.
- Authoritative request metrics retain the owning Request ID.
- Bridge IDs are never reused across independent Requests.
- Seat + Round execution identity is evaluated within the Request scope.
- No provider prose participates in the audit.

No provider credentials, model lists, cascade order, Local Engine, Paid fallback, or automatic model selection were changed.
