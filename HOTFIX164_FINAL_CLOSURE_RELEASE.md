# HOTFIX164 — FINAL CLOSURE / BRIDGE RUNTIME + CANONICAL EVIDENCE HARDENING

## Release identity

`VERSION.txt` remains the frozen production identity:

`V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`

HOTFIX164 is a hardening layer. It does not replace or rewrite the frozen provider identity contract.

## Root-cause fixes

1. **Provider-prompt control-plane isolation**
   Gemini no longer receives `bridge_id` or `round_id` through the sanitized Bridge capability projection. Bridge keys and values remain application-private.

2. **Actual runtime HTTP evidence**
   Real orchestrated Bridge requests are explicitly marked with
   `HOTFIX164-ACTUAL-RUNTIME-HTTP-BRIDGE/v1` and are fail-closed unless the canonical Bridge audit proves the actual target HTTP payload was attested and contained neither the bridge value nor the bridge key.

3. **Bridge identifier isolation**
   The Bridge audit now records whether the Bridge ID crossed the user prompt, Gemini input prompt, or target HTTP payload, and whether control-plane round identity entered the Gemini prompt/payload.

4. **Complete transactional lifecycle**
   Real Bridge closure requires the exact lifecycle:

   `WRITE → VALIDATE → COMMIT → BARRIER → READ`

   plus `MATCH=PASS` and exactly one Bridge identity per Request.

5. **Application-owned READ remains private**
   The committed Bridge value is resolved by the application control plane after the target provider request. In real transactional Bridge mode the private value is no longer copied into assistant content/history.

6. **Canonical audit hardening**
   `conversation_v25_runtime.authoritative_audit()` now distinguishes historical/synthetic Bridge fixtures from real orchestrated Bridge requests. A real Bridge request must carry the HOTFIX164 runtime-proof contract before it can contribute to final Bridge closure.

7. **Production platform fail-closed gate**
   `build_v23_platform_audit()` requires the full HOTFIX164 runtime evidence set for requests explicitly marked as real Bridge tests, while preserving compatibility for older non-runtime synthetic regression fixtures.

## Regression preservation

The original HARDENED base passed all existing tests before HOTFIX164 changes. No existing test was edited, skipped, or xfailed.

A new regression suite was added:

`tests/test_hotfix164_final_runtime_bridge_closure.py`

It covers:

- Gemini prompt control-plane identity isolation.
- Two real orchestrator Requests with two canonical Messages and two canonical Rounds.
- Distinct Bridge IDs per Request.
- DeepSeek Seat 7 → Gemini Seat 2 lifecycle closure.
- Actual runtime HTTP payload attestation and payload isolation.
- Canonical authoritative Bridge proof.
- Private Bridge-value non-persistence in assistant result content/history.
- Production platform fail-closed runtime proof.
- Fail-closed rejection when Bridge ID leaks into provider prompt/payload.

## Verification

Full local regression result after HOTFIX164:

`589 passed`

The release ZIP is built with project files directly at archive root. Build caches (`.pytest_cache`, `__pycache__`, `*.pyc`) are excluded. No ZIP is nested inside the release ZIP.
