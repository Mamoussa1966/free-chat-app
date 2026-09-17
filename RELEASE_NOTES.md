# V22.1-HOTFIX112-PRODUCTION-HARDENED

## HOTFIX112 — Clean Production Tree / Mixed-Tree Isolation Repair

HOTFIX112 is rebuilt from the verified prior release artifact as an isolated,
self-contained production tree. The release does not import or preserve unrelated
legacy files from a parent/Streamlit workspace.

### Release guarantees
- Version identity is consistently HOTFIX112 across production metadata and runtime surfaces.
- Official API only.
- Explicit `*_FREE_MODELS` only; no implicit model discovery.
- Free Cascade remains strictly sequential, bounded to ten candidates per provider.
- No Local Engine.
- No Paid fallback.
- Actual executed model identity remains authoritative and attested.
- Shared Context / transaction barriers remain fail-closed.
- Secret redaction and compact public diagnostics remain enabled.
- `.streamlit/secrets.toml.example` is preserved; real secrets are excluded.
- The release is packaged from its own isolated tree; runtime caches and symlinks are excluded.
- The production test harness resolves and tests the application-owned tree rather than unrelated sibling/parent files.

### Validation
- Clean source tree contains the complete release manifest with no deleted baseline files.
- Complete pytest suite passes from the clean source tree.
- Production Core harness passes all deterministic probes.
- Release builder packages the exact tree, re-extracts the ZIP, and reruns the complete suite from the extracted artifact.
