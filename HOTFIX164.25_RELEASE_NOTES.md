# HOTFIX164.25 — Release Contract Normalization and Regression Guard

## Release identity

The active application release label is `HOTFIX164.25`. `main.DISPLAY_VERSION` is sourced from `providers.CURRENT_HOTFIX_RELEASE_VERSION`; it is not independently duplicated. `main.PLATFORM_RELEASE_VERSION` is imported from `providers.PLATFORM_RELEASE_VERSION`, and `release_identity.py` remains the deployment identity audit source.

The frozen Provider core identity remains exactly `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`. `VERSION.txt` is intentionally unchanged.

## Report schema compatibility

The read-only explicit-target audit continues to emit `hotfix164.23-explicit-target-read-only-forensics/v1`. Application release version and report schema version are independent contracts. The v1 schema remains in place because this release does not change its wire fields or semantics; a schema bump requires an actual contract change and compatibility regression tests.

## Historical workflow isolation

The HOTFIX164.19 workflow remains available through manual dispatch as a historical-manifest and fail-closed-compatibility audit. Its automatic push trigger is removed. When run against the current branch, it verifies the historical manifest and explicitly verifies that the active runtime is not mislabeled as HOTFIX164.19; it does not pretend the current source is the historical release.

## Bridge safety

Missing or incomplete live evidence must remain `NOT_PROVEN` (or `FAIL` where a verified contradiction exists). Neither regression success nor a ZIP round-trip is live Bridge evidence. No synthetic requests, rounds, Bridge evidence, or provider execution results are permitted. No paid fallback, local engine, or dynamic model discovery is enabled.

## Validation results for this candidate

The candidate passed source validation and Python compilation, the Production Core gate, the complete regression suite (`638 passed`, `0 failed`, `0 errors` across `169` test modules), and ZIP validation followed by fresh extraction and another complete suite (`638 passed`, `0 failed`, `0 errors`). The preservation gate reported `75` previous-release files, `398` current project files, and `0` deleted previous-release files. The verified source ZIP contains `398` entries, has no nested ZIPs, and passed the builder’s path and integrity checks. These results describe this locally built candidate; no GitHub push or release was performed.

A prior explicit two-target read-only Bridge audit was previously reported as `PASS` for those exact targets only. This packaging run does not revalidate or extend that live evidence. Overall live closure remains `NOT_PROVEN` here, and any missing or incomplete new live evidence must remain `NOT_PROVEN` (or `FAIL` where a contradiction is established).
