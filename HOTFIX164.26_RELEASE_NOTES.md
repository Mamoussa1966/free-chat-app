# HOTFIX164.26 — Canonical Bridge Evidence Rehydration + Corrected Runtime Closure Report

## Core fix retained

For `STRICT_LIVE`, the canonical V26.3 RequestRecord remains the authority for application-owned Bridge evidence. Audit and sanitized export recover evidence from the canonical request record, bind it to its exact Request ID and Round ID, reject sidecar-only evidence and fail closed on conflicts. Auditing remains read-only and does not allocate requests, rounds, bridges, or provider work.

## Corrected deployed runtime report

The final user-provided read-only application audit selects the correct Request IDs:

- Run A: `6d3429f1dae84863a362e3abbc7aede2` — Round 1 — Bridge hash `40a81e4d2578d195657866ab9262e85df878a418769ed0bf42aa0d48e8feed79` — `PASS`.
- Run B: `efc1820735ba45ddb9eb04e676ec795a` — Round 2 — Bridge hash `eeb14331b7f73edfae50b0ee4d71a6fcd7a1c18424b83c102091f674ab76f74f` — `PASS`.

The aggregate application report, strict-live proof, target bindings and target independence are all `PASS`, with no blockers. It reports 2 canonical Messages / 2 Requests / 2 Rounds, four persisted application-owned runtime execution events, one Bridge evidence record and one ledger projection per target, and two distinct request-bound Bridge hashes. The earlier report using `274521681c3b49b68bf988c128803b69` and `317d3f311ffe4ff782eeff2fa4351454` was a stale-target attempt and returned `NOT_PROVEN`; it is not the report accepted by this package.

## Regression and proof boundary

The complete test suite validates software regressions and the supplied report acceptance gate. It does not invoke DeepSeek or Gemini, and it does not manufacture runtime events. Live execution is asserted only as reported by the deployed application's final application-owned audit output, recorded in `evidence/HOTFIX164.26_RUNTIME_BRIDGE_AUDIT.json`. Missing or contradictory evidence must continue to fail closed.

## Preserved provider contracts

- Frozen provider identity: `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`.
- Official API only; explicit `*_FREE_MODELS`; no Local Engine; no paid fallback; no dynamic model discovery.
- `VERSION.txt` unchanged; read-only report schema remains `hotfix164.23-explicit-target-read-only-forensics/v1`.
