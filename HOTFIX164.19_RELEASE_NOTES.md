# HOTFIX164.19 — Read-Only Request-3 Forensics and Fail-Closed Closure

## Purpose

HOTFIX164.19 addresses the observed `V23_FULL_PLATFORM_AUDIT (24).json` failure without creating another Council Request or changing the canonical Message → Request → Round history. It separates identity-counter consistency from result/execution-artifact completeness, keeps final closure blocked when the Platform audit fails, and adds a dedicated read-only page for inspection of already-persisted runtime records.

## Root cause supported by the audit export

- The canonical store reports **3 Messages / 3 Requests / 3 Rounds**, with a valid identity chain and a passing canonical preflight.
- The full Platform audit is nevertheless **FAIL** because the latest Request (`4cec624c0c98491a8831d34fe6b37255`) lacks required persisted execution/result artifacts: `SEAT_RESULTS`, `EXECUTED_MODELS`, `CASCADE_SUMMARIES`, `FINAL_RESULT`, and `AUTHORITATIVE_METRICS` are false. Its continuation runtime gate is `NOT_PROVEN`.
- The exported execution accounting reports four `execution_started` events, all associated with the first two Request IDs. It does not list the third Request as executed, and it records no explicit `NOT_EXECUTED` classification for that Request. Therefore the third Request's execution state is **NOT_PROVEN**, not success and not proof of non-execution.
- The old persistence audit calculated `counter_semantics_consistent` as `ok AND persisted_counts_match`. Since `ok` also depends on unrelated per-Request result artifacts, missing third-Request artifacts incorrectly made an otherwise matching canonical 3/3/3 count appear semantically inconsistent. HOTFIX164.19 separates these facts but does not change the overall FAIL decision.
- The strict live Bridge report proves only the two Requests that were flagged `STRICT_LIVE`; both are `PASS` in that export. Request 3 was not requested as a strict live Bridge transaction, so it has no Bridge closure claim.

## Changes

- Added `read_only_existing_records_audit`, which reads a deep copy of current records, reports each canonical Request's message/round binding, execution identity, results, actual-model evidence, cascade summaries, synthesis, metrics, and applicable Bridge status. It never uses UI message counts to make canonical identity claims and never fills missing evidence.
- Added an isolated HOTFIX164.19 UI path that intercepts the action before normal state initialization, hydration, index reconstruction, health checks, context building, test harnesses, provider calls, cascades, or Bridge writes. It presents and downloads a sanitized JSON audit and returns a fail-closed `NOT_PROVEN` when required evidence is missing.
- Corrected `conversation_persistence_audit.counter_semantics_consistent` to describe the canonical counter relation and preflight, independently of required per-Request artifacts. The persistence status continues to be `FAIL` while mandatory artifacts are missing, and `failure_reasons` names each missing artifact.
- Hardened `build_v23_final_closure_audit`: final closure now requires `platform_report.status == PASS` and `conversation_persistence.status == PASS` as well as consistent canonical identity and a passing security audit. Matching counts cannot turn a failed Platform audit into closure PASS.
- Updated only the current runtime release label and the release-label regression to HOTFIX164.19. `VERSION.txt` remains exactly `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`.
- Preserved official-API-only execution, explicit free cascade, provider order, V26.3 identity allocation, no Local Engine, no paid fallback, and no dynamic model discovery.

## Acceptance boundary

The local package is accepted only if the full regression suite, Production Core harness, source validation, ZIP integrity, root-layout, and freshly extracted full regression all pass. This validates the candidate code and read-only diagnostic path; it does **not** establish that the published Streamlit application is already updated or that the third Request has executed. The supplied audit still shows Request 3 `NOT_PROVEN`. No new Request, Round, Bridge, or provider execution was created during this package build.
