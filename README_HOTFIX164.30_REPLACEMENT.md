HOTFIX164.30 — TARGETED REPLACEMENT FILES

Purpose
Fix the two independent closure-gate failures observed in GitHub Actions run 39280489035.

Files in this archive (both belong at repository root):
- HOTFIX164.30_DEPLOYMENT_COMMIT_GATE.py
- build_release.py

Changes
1. The independent gate validates providers.py CURRENT_HOTFIX_RELEASE_VERSION against EXPECTED_APP_IDENTITY. It also requires manifest.deployed_release_label to equal EXPECTED_APP_IDENTITY.
2. build_release.py writes the checksum sidecar next to the requested ZIP output, e.g. dist/HOTFIX164.30_FULL_RELEASE_CANDIDATE.zip.sha256.

Preservation
VERSION.txt and V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE are unchanged. No Bridge runtime or V26.3 canonical persistence code was changed. Tests were not modified.

Deployment/verification note
This replacement package does not itself deploy the app or prove live final closure. After these files reach the deployed revision, export fresh deployment-bound evidence from that running app and rerun the HOTFIX164.30 deployed-commit closure workflow. Closure is proven only if that run reports status=PASS and live_final_closure_proven=true.
