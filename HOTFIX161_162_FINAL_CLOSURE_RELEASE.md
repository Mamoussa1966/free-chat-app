# HOTFIX161/162 — V23 Final Closure Candidate

Scope: additive closure over the HOTFIX160 release candidate. No historical test is disabled or rewritten to manufacture PASS.

Implemented closure hardening:
- Request creation owns monotonic `canonical_round_base` allocation.
- Canonical Request records expose the HOTFIX161/162 allocation contract.
- Canonical persistence audit now exposes authoritative persisted Message/Request/Round counts and requires them to match the canonical record and preflight.
- Gemini-target Bridge prompts redact committed Bridge values even when the value is present in shared context.
- HOTFIX135 multi-request audit exposes explicit isolation checks while retaining fail-closed status semantics.
- Added regression coverage for canonical round materialization, message `round_id`, hydration indexes, persistence counters, multi-request isolation, and Gemini no-secret behavior.
- `.streamlit/secrets.toml.example` is preserved; no credentials are included.

Validation policy:
- Existing release suite must remain green.
- New regression tests must pass for the closure changes.
- This artifact is a closure candidate, not a claim of final production PASS unless the complete external V23 audit also returns PASS / FAILED=0.
