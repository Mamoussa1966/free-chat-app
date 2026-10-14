# HOTFIX164.18 — Request-Scoped Bridge Proof Diagnostics

## Purpose

HOTFIX164.18 adds an explicit, sanitized per-Request diagnosis to the security audit so a two-Request closure report identifies which strict live Bridge proof is `PASS`, `NOT_PROVEN`, or `FAIL`. It is a diagnostic and regression-closure release above HOTFIX164.17, not evidence that a deployed live conversation has passed.

## Changes

- Add `strict_live_bridge_proof` to `security_audit`, including one record per strict live Bridge Request.
- Report missing application-owned evidence and missing identity/round attestations as `NOT_PROVEN`; report explicit identity mismatches, contradictory evidence, detected boundary leaks, and reused Bridge hashes as `FAIL`.
- Keep the existing security gates fail-closed. Missing or incomplete proof still makes the security audit and final closure fail; the new diagnostic cannot promote it to `PASS`.
- Export only Request identity, sanitized status fields, and reason codes. Raw Bridge IDs, Bridge hashes, Bridge values, prompts, credentials, and HTTP bodies are not copied into the new diagnostic.
- Advance the room's active release heading to HOTFIX164.18 while preserving `VERSION.txt` exactly as `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`.
- Preserve V26.3 Message → Request → Round allocation, canonical counters, provider dispatch order, official API-only execution, explicit free-model cascade, and the no-paid-fallback/no-local-engine/no-dynamic-discovery policy.

## Local candidate validation

- Targeted Bridge/security regression: **31 passed, 0 failed**.
- Full regression suite: **627 passed, 0 failed, 0 errors**.
- Full regression on the freshly extracted ZIP: **627 passed, 0 failed, 0 errors**.
- Production-core gate, file-preservation gate, and ZIP round-trip: **PASS**.

## Acceptance boundary

The ZIP is built only after source tests, full regression tests, production-core checks, extraction, and extracted-copy tests pass. This local candidate does not claim that it was uploaded to GitHub, that a GitHub Actions run passed for HOTFIX164.18, or that the live deployed two-Request Bridge proof is closed. A live acceptance audit must show complete application-owned evidence and distinct Bridge hashes for every strict live Request actually requested in the test.
