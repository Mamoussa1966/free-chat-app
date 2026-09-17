# HOTFIX93 — PRODUCTION CORE TEST HARNESS

Version: `V22.1-HOTFIX93-PRODUCTION-HARDENED`

## Purpose

HOTFIX93 is built directly from the complete HOTFIX93 ZIP. It adds a real executable Production Core Test Harness so validation is performed by Python/pytest in an execution environment, not by asking provider agents to claim they ran tests.

## Preserved baseline

- All 69 previous release ZIP members are required to remain present.
- All HOTFIX93 files are preserved.
- HOTFIX93's `production_core.py` remains the Production Core implementation.
- No Local Engine, Paid fallback, or automatic model selection is introduced.

## Added

1. `production_core_harness.py`
   - real subprocess execution of the full pytest suite
   - credential-environment scrubbing
   - previous release file-preservation check
   - deterministic lifecycle/cascade/model-identity/false-success/context-transaction/secret-redaction probes
   - explicit `PASS` / `NO-GO` gate
2. `previous release_FILE_MANIFEST.json`
   - immutable file-preservation reference derived from the complete previous release release ZIP
3. `tests/test_hotfix93_test_harness.py`
   - regression coverage for harness execution and preservation invariants

## How to run

```bash
python production_core_harness.py
```

The command runs the real test suite through Python's pytest module invocation and exits with code `0` only when the Production Core gate passes.

## Important boundary

The harness does not claim that an external provider API is free or available. Provider integration tests remain isolated and use their existing project contracts. No secrets are printed or required by the harness.
