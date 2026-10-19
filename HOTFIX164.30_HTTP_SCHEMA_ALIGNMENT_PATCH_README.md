# HOTFIX164.30 — HTTP Attestation Schema Alignment Patch

## Why this patch exists
The deployed runtime exporter in `main.py` emits `hotfix164.29-runtime-http-attestation/v1`. The independent HOTFIX164.30 gate incorrectly expected `hotfix164.30-runtime-http-attestation/v1`, even though the manifest states that the HTTP wire schema is independently versioned from the application release. This mismatch prevents a valid report from passing.

## Files in this ZIP
- `HOTFIX164.30_DEPLOYMENT_COMMIT_GATE.py` — expects the existing exporter schema.
- `HOTFIX164.30_RELEASE_MANIFEST.json` — documents the schema contract and corrected validation accounting.
- `tests/test_hotfix16430_http_schema_alignment.py` — regression tests keeping exporter and gate schema in sync.
- `HOTFIX164.30_RELEASE_NOTES.md` and `HOTFIX164.30_FINAL_CLOSURE_STATUS.md` — record the fix and retain NOT_PROVEN closure status.

## Apply
Extract this ZIP at the repository root, preserving paths, and commit the replacements/addition to `gitops-v0.4-final`. Wait for the deployed app to report the new commit. Run two new real Bridge requests and export a fresh `HOTFIX164.30_DEPLOYMENT_BRIDGE_EVIDENCE.json`. Then run the HOTFIX164.30 deployment-commit closure workflow with that evidence.

## Validation
- Full local pytest regression: **666 passed, 0 failed, 0 errors**.
- Independent release-builder ZIP round-trip: **NOT_PROVEN** (the release-builder command timed out during its sandbox pass; do not treat this patch ZIP as a full release candidate).
- Deployed commit-bound final closure: **NOT_PROVEN** until a fresh report from the redeployed commit passes the independent gate.
