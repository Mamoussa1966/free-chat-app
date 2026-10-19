# HOTFIX164.30 Automation Foundation (candidate)

This layer adds automation configuration on top of the frozen HOTFIX164.30 source baseline. It does not modify application/runtime logic, `VERSION.txt`, canonical V26.3 persistence, bridge behavior, or tests.

## Included controls

- `.github/workflows/ci.yml`: pull-request, push, and manual CI. It uses read-only repository permissions, pins GitHub Actions to immutable commit SHAs, checks frozen release identity, invokes `build_release.py` (which runs the release validation, production-core harness, full regression suite, ZIP round-trip suite), verifies the SHA-256 sidecar, then publishes a 14-day CI artifact. This job is offline with respect to provider APIs and does not need provider secrets.
- `.github/dependabot.yml`: weekly dependency-update PRs for Python and GitHub Actions. Dependabot opens PRs; it does not self-approve or merge them.
- `.github/rulesets/gitops-v0.4-final.ruleset.json`: repository ruleset definition for the production branch. This file is a configuration payload/reference and is **not automatically enforced merely because it exists in the repository**. Apply/import it in GitHub Settings → Rules → Rulesets after the CI workflow has completed successfully once and the required status-check context `CI / regression-and-package` is visible.

## Required rollout sequence

1. Extract the replacement package at the repository root, preserving `.github/` paths, or add these files through a branch/PR.
2. Open a pull request targeting `gitops-v0.4-final`; confirm `AI Council CI` passes.
3. Verify the successful CI run produced the candidate ZIP and sidecar.
4. Apply the included ruleset in repository settings. Confirm it targets only `refs/heads/gitops-v0.4-final` and requires `CI / regression-and-package`.
5. Merge the automation foundation only after the CI check has passed.
6. Once this new commit is deployed, run the existing HOTFIX164.30 deployed-commit closure with fresh application-exported evidence bound to the exact deployed commit. Do not reuse the prior evidence JSON for a new commit.

## Fail-closed contract

- `VERSION.txt` remains `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`.
- Frozen application identity remains `HOTFIX164.30 — DEPLOYED-COMMIT-BOUND LIVE CLOSURE`.
- Existing bridge and V26.3 tests remain mandatory and unchanged.
- No test is skipped or weakened to achieve a pass.
- CI success proves that this source candidate passed its configured checks; it does **not** prove that the new commit is deployed or that live closure passed. Those require the existing deployed-commit-bound live gate with fresh runtime evidence.
- Branch protection is enforced by GitHub repository settings, not by the presence of the JSON file alone.
