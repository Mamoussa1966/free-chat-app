# V22.1-HOTFIX96-PRODUCTION-HARDENED

## HOTFIX96 — Production Core / Council Orchestrator Hardening

This release is rebuilt from the verified previous verified release Production-Hardened baseline and advances the release identity to HOTFIX96 without removing the retained release files or tests.

### Fixed in HOTFIX96
- Canonical release identity is synchronized across VERSION.txt, providers.py, main.py, Production Core, README, build_release.py, and the test suite.
- Release metadata no longer contains stale historical HOTFIX identifiers.
- Release-consistency tests are version-agnostic for historical regression modules instead of pinning an old release number.
- `.streamlit/secrets.toml.example` remains included as a regular release file.
- Runtime secrets are excluded from the release artifact.
- File preservation remains fail-closed; the canonical release tree is retained rather than replaced by a reduced file set.
- Production Core remains application-owned and offline: providers are never asked to execute pytest or shell commands.
- Free Cascade remains #1→#10 per provider, Official API only, with no Local Engine and no Paid fallback.
- Actual executed-model identity, Shared Context, Transaction Guard, false-success protection, and secret redaction remain enforced.

### Verification contract
The release is not considered ready unless all retained tests pass, the ZIP is structurally valid, and the Production Core harness returns PASS.

### Deployment note
This ZIP is the canonical HOTFIX96 artifact. A Streamlit deployment must be redeployed from this exact tree; a previously deployed mixed/stale tree is not evidence of the contents of this artifact.
