# HOTFIX126 — CONTINUATION IDENTITY + BRIDGE AUDIT HARDENING

Fixes only the current runtime failures:
- A persisted completed REQUEST_ID is recognized as continuation even if the UI omits the word continuation.
- Continuation remains fail-closed and READ_ONLY: no new Request, Round, Provider, Cascade, or Bridge.
- Full platform audit rejects multiple persisted Bridge IDs for one Request.
- Unknown Request IDs never fall through to new Request allocation.
- Existing files, Secrets, and model lists are preserved.
