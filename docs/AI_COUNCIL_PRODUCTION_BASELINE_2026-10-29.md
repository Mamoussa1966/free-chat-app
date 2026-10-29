# AI Council Production Baseline — 2026-10-29

## Purpose and safety boundary

This record pins the stable production source before follow-on work. It does not change the production branch, Streamlit configuration, Supabase schema, provider configuration, or credentials. All follow-on work starts from a separate branch and must pass Pull Request checks before any merge.

## Authoritative production source

- Repository: `Mamoussa1966/free-chat-app`
- Production branch: `gitops-v0.4-final`
- Baseline commit: `aa55bd6474b59288f962bb531801aac60e196624`
- Commit: https://github.com/Mamoussa1966/free-chat-app/commit/aa55bd6474b59288f962bb531801aac60e196624
- Frozen provider/core identity from `VERSION.txt`: `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`
- Application release identity: `HOTFIX164.30 — DEPLOYED-COMMIT-BOUND LIVE CLOSURE`

## Deployment-bound closure evidence

- Closure workflow run: https://github.com/Mamoussa1966/free-chat-app/actions/runs/40807383965
- Result: `success`
- Run SHA (evidence/workflow commit): `c86648afa53b8748b26a0001834c213daf861acc`
- Verified deployed application source SHA reported by the gate: `aa55bd6474b59288f962bb531801aac60e196624`
- Workflow log asserted `HOTFIX164.30_DEPLOYED_COMMIT_FINAL_CLOSURE=PASS`.
- The closure workflow ran on the evidence branch; it did not update the production branch.

## Permanent release archive and SHA-256

The exact production baseline was archived after a separate successful verification workflow:

- Permanent GitHub Release: https://github.com/Mamoussa1966/free-chat-app/releases/tag/HOTFIX164.30-BASELINE-2026-10-29
- Release tag: `HOTFIX164.30-BASELINE-2026-10-29`
- Archival workflow: https://github.com/Mamoussa1966/free-chat-app/actions/runs/40810998432
- Archival workflow result: `success`
- The workflow checked out and verified exactly `aa55bd6474b59288f962bb531801aac60e196624`, then passed compilation, the complete offline regression suite, ZIP integrity and the detached SHA-256 sidecar check.
- Archive: [HOTFIX164.30_BASELINE_PROJECT.zip](https://github.com/Mamoussa1966/free-chat-app/releases/download/HOTFIX164.30-BASELINE-2026-10-29/HOTFIX164.30_BASELINE_PROJECT.zip)
- Archive size: `798857` bytes
- Archive SHA-256: `cc8f521510a1e9a674dda2d55a938d07ff85b59a18db71b1567bee43c9ea744c`
- Detached checksum: [HOTFIX164.30_BASELINE_PROJECT.zip.sha256](https://github.com/Mamoussa1966/free-chat-app/releases/download/HOTFIX164.30-BASELINE-2026-10-29/HOTFIX164.30_BASELINE_PROJECT.zip.sha256)
- Release manifest: [RELEASE_MANIFEST.json](https://github.com/Mamoussa1966/free-chat-app/releases/download/HOTFIX164.30-BASELINE-2026-10-29/RELEASE_MANIFEST.json)

The separate verified-closure Actions artifact remains available as secondary evidence until `2026-11-28`:
- Artifact name: `HOTFIX164.30-deployed-commit-closure-verified-candidate`
- Artifact ID: `12868926545`
- GitHub artifact digest: `sha256:cbfbbba89eb8d0fea42d4a56185da291532086ff43d760686e5476e4cf98a233`
- Workflow: https://github.com/Mamoussa1966/free-chat-app/actions/runs/40807383965

The accompanying diagnostic artifact is `12868757566`, digest `sha256:895e609c20a15ceece9e9e5e6d72549b42a43da1fbab418c72aebaf9fa2a8845`, also expiring on `2026-11-28`.

## Manual production smoke tests

The operator reported these five checks as PASS on 2026-10-29:

| Test | Reported result |
|---|---|
| Login and open the conversation room | PASS |
| Send text and see agent results | PASS |
| Refresh and retain the conversation | PASS |
| Record voice and transcribe it to text | PASS |
| Delete a conversation and its associated voice recordings | PASS |

These are explicitly **operator-reported manual results**, not claims that CI automated browser access to the production session.

## Existing controls observed in source

- CI runs on pushes and Pull Requests to `gitops-v0.4-final`; it checks the frozen core/release identity, runs the release build/test path, validates the ZIP and SHA-256 sidecar, and uploads a candidate artifact.
- The app already includes provider diagnostics, explicit Free-model configuration display, non-secret credential source diagnostics, and persisted last-execution status/reason for agent seats.
- Official API / explicit Free-model behavior remains authoritative; no Local Engine, paid fallback, dynamic model discovery, or credential exposure is introduced by this work.
- The deployment-bound closure workflow remains a separate test from general CI. Green CI by itself is not deployment proof.

## Outstanding follow-up

1. Add the scheduled source/CI/closure-status report in the isolated development branch.
2. Validate that report script with unit tests and the existing CI on a Pull Request.
3. Publish a permanent baseline release archive plus SHA-256 sidecar after the tested source ref is selected; do not modify the deployed branch as part of this archival step.
4. Keep product/UI enhancements in separately scoped Pull Requests after the source/CI observability change passes.
