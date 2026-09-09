# V22.1 Final Hotfix 3

## Fixed / hardened

- Preserved the strict 20-provider registry and explicit Free-only cascade of up to 10 models per provider.
- Normalized direct `call_seat()` model inputs through the same parser/deduplication/10-model safety cap used by Secrets.
- Made HTTP 401, 403, 404, and 429 classification explicit and stable.
- Kept 429 billing/credit/quota failures distinct from ordinary rate limiting.
- Prevented 404 resource errors from blindly cascading to unrelated models.
- Kept authentication/permission failures terminal for a provider seat.
- No Local Engine, no hidden model, and no automatic paid fallback.
- Added/retained pytest as the test dependency and verified the complete suite.

## Verification

- Python bytecode compilation: passed.
- Test suite: 39/39 passed.

## Free-model policy

The runtime never claims that a model is free merely because it is publicly listed. Each model must be explicitly configured by the deployment owner in the relevant `*_FREE_MODELS` Secret/environment variable and must be entitled by that provider account at zero cost.


## GitOps V0.4 Hardened layer

- Added independent `gitops_layer.py` with canonical-path validation, default-deny mutable-file allowlist, AST policy checks, workspace manifest hashing, candidate-workspace test gating, approval/hash binding, expiry checks, and simulated GitHub boundary validation.
- Added `tests/test_gitops_layer.py` with 39 adversarial regression tests covering path traversal, protected files, AST bypass attempts, snapshot/diff hashes, candidate tests, timeout handling, attestation, approval, and TOCTOU.
- GitOps push remains simulated/disabled; no GitHub network push is performed by this release.

## Verification

- `python -m compileall -q .`: passed.
- `python -m pytest -q`: **78 passed** (39 existing V22.1 tests + 39 GitOps tests).
