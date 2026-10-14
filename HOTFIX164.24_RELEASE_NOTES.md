# HOTFIX164.24 — Canonical Bridge Evidence Persistence and Round-Bound Ledger

## Release-contract correction

This release aligns the application display label, `providers.CURRENT_HOTFIX_RELEASE_VERSION`, the current release manifest, the provider-runtime regression test, and the GitHub Actions release gate at `HOTFIX164.24`. The frozen provider identity in both `providers.VERSION` and `VERSION.txt` remains exactly `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`.

## Scope and safety

- The `HOTFIX164.18_RUNTIME_LABEL_FAILED` assertion is corrected at its source by aligning the runtime label and workflow contract; the assertion is not skipped or weakened.
- The release builder's baseline allowlist explicitly permits the versioned workflow update while preserving all baseline files and all existing tests.
- Strict Bridge closure remains fail-closed. Missing canonical request records, application-owned Bridge evidence, or request/round-bound ledger projection must remain `NOT_PROVEN` or `FAIL`.
- The release manifest explicitly records `live_final_closure_proven: false`; a green regression suite is not live Bridge closure evidence.
- No paid fallback, local engine, dynamic model discovery, synthetic execution results, or synthetic Bridge evidence is enabled.

## Validation

The GitHub Actions workflow must pass source validation, production-core gate, the full regression suite, release ZIP validation, and a fresh ZIP-extraction test before its release artifact is accepted. This document does not claim that those gates have passed until their actual output is available.
