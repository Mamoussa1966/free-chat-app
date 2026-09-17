# V22.1-HOTFIX99-PRODUCTION-HARDENED

## HOTFIX99 — Clean Production Release / Full Test-Passing Build

HOTFIX99 is rebuilt from the verified clean Production-Hardened release tree.

### Release guarantees
- Version identity is consistently HOTFIX99 across production metadata and runtime surfaces.
- Official API only.
- Explicit `*_FREE_MODELS` only; no implicit model discovery.
- Free Cascade remains strictly sequential, bounded to ten candidates per provider.
- No Local Engine.
- No Paid fallback.
- Actual executed model identity remains authoritative and attested.
- Shared Context / transaction barriers remain fail-closed.
- Secret redaction and compact public diagnostics remain enabled.
- `.streamlit/secrets.toml.example` is preserved while real secrets are excluded.
- All existing test modules are preserved.

### Validation
The release builder runs the Production Core harness, the complete pytest suite, packages the exact tree, checks the ZIP manifest, and re-extracts/re-runs the suite from the resulting artifact.
