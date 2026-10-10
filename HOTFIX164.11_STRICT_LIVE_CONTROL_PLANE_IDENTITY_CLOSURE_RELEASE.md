# HOTFIX164.11 — Strict Live Control-Plane Identity Closure

## Purpose

This release addresses the three regressions reported against HOTFIX164.10 while preserving the frozen provider-core identity and the existing V26.3 canonical lifecycle contract.

## Changes

- Added strict, explicit audit fields for Bridge ID presence in user prompts, provider prompts, Gemini input, and Gemini HTTP payloads, alongside Request ID and canonical Round ID checks.
- Replaced substring matching for short symbolic control-plane identities with whole-token matching; opaque production IDs continue to use exact full-string matching. This avoids false-positive leaks such as a short identifier being found inside an unrelated word.
- Recorded the sanitized user-prompt and shared-context components separately for boundary auditing; the audit checks their combined actual provider-input boundary.
- Exposed per-message Bridge proof-obligation and proof-status fields in the canonical final audit. Missing required proof remains `NOT_PROVEN`; explicit leakage remains `FAIL`.
- Made platform persistence, regression, and security audits merge richer direct request data into canonical request history without allowing a narrow current-request projection to erase historical canonical rows.
- Added targeted HOTFIX164.11 regression coverage for actual orchestrator flow, fail-closed behavior, platform audit integration, intentional control-plane identity leakage, and prompt sanitization.

## Frozen contracts preserved

- `VERSION.txt` remains `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`.
- No Local Engine, no Paid fallback, no dynamic model discovery.
- Canonical Message → Request → Round counts remain sourced from canonical identity records.
- Strict Bridge evidence is application-owned; provider prose is not an authority for runtime proof.

## Validation

- Targeted HOTFIX164.11 closure tests: **4 passed**.
- Related HOTFIX164.10 security, HOTFIX164.9 live evidence, and HOTFIX164.2 orchestration tests: **17 passed**.
- Full test suite: **611 passed, 0 failed**.
- Fresh ZIP extraction full test suite: validated separately before release.

These repository tests do not substitute for a successful deployed live-room export. Live closure remains unproven until the deployed application exports two distinct, complete application-owned Bridge records bound to the two canonical requests/rounds and its strict platform/security audit passes.
