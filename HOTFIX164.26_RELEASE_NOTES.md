# HOTFIX164.26 — Canonical Bridge Evidence Rehydration + Corrected Runtime Closure Report

## Core fix retained

For `STRICT_LIVE`, the canonical V26.3 RequestRecord remains the authority for application-owned Bridge evidence. Audit and sanitized export recover evidence from the canonical request record, bind it to its exact Request ID and Round ID, reject sidecar-only evidence and fail closed on conflicts. Auditing remains read-only and does not allocate requests, rounds, bridges, or provider work.

## Latest deployed runtime report supplied by the user

- Run A: `5acf12d46319424082fce5db5a1be9f2` — Round 1 — Bridge hash `5e90ff8b7d09cc925cc40eff93f069ac1ced368d0782e01c40d31e99c81a8537` — `PASS`.
- Run B: `018889aa696f4be0a1ddf107e6c2ceec` — Round 2 — Bridge hash `b0696582ebb77b961ec91dd7a00e9d37270d238f7a77e1d915ae45632e28a658` — `PASS`.

The latest aggregate application report, strict-live proof, target bindings and target independence are `PASS`, with no blockers. It reports 2 canonical Messages / 2 Requests / 2 Rounds and five persisted application-owned runtime execution events (3 for A, 2 for B), one Bridge evidence record and one ledger projection per target, and two distinct request-bound Bridge hashes. The first stale-target audit with `274521681c3b49b68bf988c128803b69` and `317d3f311ffe4ff782eeff2fa4351454` returned `NOT_PROVEN`; the previously accepted run `6d3429f1dae84863a362e3abbc7aede2` and `efc1820735ba45ddb9eb04e676ec795a` is now superseded by this latest report.

## Regression and proof boundary

The complete test suite validates software regressions and the supplied report acceptance gate. It does not invoke DeepSeek or Gemini, and it does not manufacture runtime events. Live execution is asserted only as reported by the deployed application's final application-owned audit output, recorded in `evidence/HOTFIX164.26_RUNTIME_BRIDGE_AUDIT.json`. Missing or contradictory evidence must continue to fail closed.

## Preserved provider contracts

- Frozen provider identity: `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`.
- Official API only; explicit `*_FREE_MODELS`; no Local Engine; no paid fallback; no dynamic model discovery.
- `VERSION.txt` unchanged; read-only report schema remains `hotfix164.23-explicit-target-read-only-forensics/v1`.
