# HOTFIX95 REPAIR — Production Hardened

This artifact is a repair/rebuild of HOTFIX95 from the canonical HOTFIX95 source baseline.

Repair guarantees:
- Preserves the HOTFIX93 file baseline and all retained test modules.
- Preserves Production Core, Test Harness, and Test Runner.
- Free Cascade #1 -> #10 only.
- Official API only.
- No Local Engine.
- No Paid fallback.
- Actual executed-model identity remains authoritative.
- Shared Context / Transaction Guard remains fail-closed.
- Gemini and DeepSeek are never used as shell/pytest executors.
- `.streamlit/secrets.toml.example` is present.
- The canonical artifact is validated locally by the application-facing Production Core Test Harness.

Validation performed on the release tree:
- Full pytest suite: PASS
- Production Core probes: PASS
- Production Core Gate: PASS

This repair does not claim that an already-deployed Streamlit runtime has been updated until this artifact is redeployed.
