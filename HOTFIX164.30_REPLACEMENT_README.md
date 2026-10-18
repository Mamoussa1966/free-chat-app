# HOTFIX164.30 — Replacement Files Package


This is an overlay/patch package, not the complete application source archive.
Extract it at the repository root, preserving the directory structure, so each file replaces or creates the same repository-relative path.

Target repository: `Mamoussa1966/free-chat-app`
Target branch: `gitops-v0.4-final`
Frozen `VERSION.txt` / provider core identity: unchanged.

## Contents

The ZIP contains only the 14 new or modified project files listed in `HOTFIX164.30_REPLACEMENT_FILES_MANIFEST.json`, plus this README and the manifest. No parent directory is added around the paths.

## One removal to review

The HOTFIX164.30 full release archive no longer contains `HOTFIX164.26_PACKAGE_VALIDATION.json` at the repository root. ZIP overlay extraction cannot delete an existing file, so check whether that exact stale file exists in your branch; remove it only if it does and is a generated historical artifact, then commit the deletion. Do not delete any `evidence/` source record just because it is not embedded in the release ZIP.

## Acceptance

This package does **not** claim live final closure. Commit its files, deploy the new revision to Streamlit, export fresh `HOTFIX164.30_DEPLOYMENT_BRIDGE_EVIDENCE.json` from the deployed app, then run `.github/workflows/hotfix164-30-deployment-commit-closure.yml` with that evidence and the exact deployed commit SHA. Final closure is proven only when the independent workflow emits `HOTFIX164.30_DEPLOYED_COMMIT_FINAL_CLOSURE=PASS`.
