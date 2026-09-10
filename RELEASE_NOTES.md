# AI Council V22.1 — Final Exact Names Updated / Hardened Hotfix 6

## Release status

Final hardened application package for the V22.1 Free API Cascade contract.

## Fixes

1. Reworked provider configuration to use keyword-only construction semantics through explicit dataclass fields and removed implicit model defaults.
2. Enforced a hard maximum of 10 configured Free candidates per provider.
3. Removed every council Local Engine/fallback path.
4. Removed automatic paid-model selection.
5. Added credential-aware error sanitization.
6. Preserved OpenAI authentication diagnostics without pretending authentication implies a Free model.
7. Hardened retry classification so persistent billing/credit failures are not retried as if transient.
8. Hardened provider attachment payload bounds.
9. Made voice transcription require an explicitly configured model; no hidden default transcription model is inserted.
10. Added an 8 MB voice safety cap.
11. Added exact per-chat request fingerprints to reduce duplicate submissions.
12. Added DOCX archive traversal, symlink, member-count, and expansion checks.
13. Added bounded conversation history and bounded execution rounds.
14. Kept provider calls out of Streamlit secret access from worker threads.
15. Rebuilt the test suite around syntax, Free-only routing, attachment security, retry behavior, diagnostics, and entrypoint behavior.
16. Added a reproducible release checker/builder that parses every Python source before packaging and writes a SHA-256 sidecar.
17. Added a monotonic whole-council execution deadline and deadline-aware HTTP timeouts/retry sleeps.
18. Added a bounded provider response-size contract.
19. Fixed release packaging so previous ZIP/hash artifacts cannot be nested into a new ZIP.
20. Added runtime regression tests for deadline enforcement and response-size bounding.
21. Added HTTPS endpoint enforcement and model-ID path-traversal rejection.
22. Added a hard provider response-body cap before JSON parsing.
23. Added bounded deadlines to diagnostics and Gemini voice transcription.
24. Added regression tests for the new endpoint/body/path hardening.

## Explicit non-claims

- The application does not certify that a configured model is free; the provider account determines that entitlement.
- HTTP/API success does not prove indefinite quota or future availability.
- Python-level hardening is not an operating-system sandbox.
- No application inside a user-controlled deployment can guarantee tamper resistance against the same principal controlling its code and secrets.
