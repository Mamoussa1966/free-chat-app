# V22.1-HOTFIX98-PRODUCTION-HARDENED

## HOTFIX98 — Clean Release Tree / Production Core Continuity

HOTFIX98 is rebuilt directly from the verified previous verified artifact as a clean, deterministic release tree. The previous verified artifact contains exactly 75 files (excluding the two directory entries) and includes `.streamlit/secrets.toml.example`.

### Scope
- Preserve the complete verified previous file tree; no historical files are imported from the deployment workspace.
- Preserve the full retained test suite and its exact test-file set.
- Advance the canonical release identity to HOTFIX98 across the current production metadata.
- Keep Production Core, Request Lifecycle, Provider Execution Contract, Free Cascade #1→#10, actual-model attestation, false-success protection, Shared Context / Transaction Guard, and secret redaction unchanged in behavior.
- No Local Engine, no Paid fallback, no implicit model discovery, and Official API only.
- Runtime secrets remain excluded; `.streamlit/secrets.toml.example` is included as a regular release file.

### Clean-tree deployment contract
The ZIP is the canonical HOTFIX98 artifact. Deployment must use this exact ZIP/tree rather than merging files into an existing checkout. A mixed runtime tree is not part of the artifact and must not be used as release evidence.

### Verification
Release acceptance requires source compilation, the Production Core harness PASS result, the complete pytest suite PASS result, ZIP structural validation, exact test-set preservation, and a second full-suite run from the extracted ZIP.
