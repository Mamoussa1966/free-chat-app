# HOTFIX94 — REAL IN-APP PRODUCTION CORE TEST RUNNER

Version: `V22.1-HOTFIX94-PRODUCTION-HARDENED`

## Baseline preservation

HOTFIX94 is built from the complete previous release release ZIP. No previous release file is deleted or replaced by a reduced subset.

- previous release ZIP members preserved: 73/73.
- New HOTFIX94 files are additive only.
- `BASELINE_FILE_MANIFEST.json` records the complete previous release file set used by the in-app preservation gate.

## Production Core validation path

The application now owns the validation path:

`Run Production Core Tests` → `production_core_test_runner.py` → `production_core_harness.py` → real local pytest + deterministic Production Core probes → `PASS` / `NO-GO`.

The request is executed by the application's Python runtime. It is not sent to Gemini, DeepSeek, Claude, Grok, Kimi, or ChatGPT for execution.

## Added

1. `production_core_test_runner.py`
   - application-facing runner
   - calls the local harness directly
   - returns the real exit code and structured report
2. `production_core_harness.py`
   - real `python -m pytest -q` execution
   - credential/environment scrubbing
   - previous release file-preservation gate
   - deterministic Production Core contract probes
   - final `PASS` / `NO-GO` gate
3. `tests/test_hotfix94_test_runner.py`
   - verifies the runner is wired to the harness
   - verifies the HOTFIX94 release identity
   - verifies the Streamlit UI exposes the runner
4. Streamlit UI
   - sidebar button: `🧪 Run Production Core Tests`
   - displays the actual harness report and gate result in the application

## Execution boundary

The Test Harness does not fabricate provider results and does not require provider credentials. Existing provider integration tests remain governed by their own fixtures/contracts. No Local Engine, paid fallback, or automatic model selection is introduced.

## CLI

```bash
python production_core_test_runner.py
```

or:

```bash
python production_core_harness.py
```
