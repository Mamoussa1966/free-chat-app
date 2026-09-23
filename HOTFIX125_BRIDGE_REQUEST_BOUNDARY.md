# HOTFIX125 — BRIDGE REQUEST BOUNDARY / FAIL-CLOSED GATE

Bridge-only corrective patch over the existing HOTFIX124 artifact and frozen deployed identity.

## Contract

A Request has exactly one of two Bridge modes:

- `bridge_test_requested = false`: Bridge is **NOT_REQUESTED**. No Bridge transaction is created, no Bridge audit is rendered, and absence of Bridge evidence is not a failure.
- `bridge_test_requested = true`: the Bridge transaction is mandatory. Missing or incomplete authoritative Bridge evidence is **FAIL**, never PASS and never silently converted to NOT_REQUESTED.

Bridge activation is explicit and request-scoped. The legacy diagnostic phrase `TRANSACTIONAL BRIDGE ISOLATION` remains a supported explicit activation token; application-generated bridge controls also activate the Bridge mode.

## Production gate

When Bridge Test is requested, all ten checks are mandatory:

`WRITE=PASS`
`VALIDATE=PASS`
`COMMIT=PASS`
`BARRIER=PASS`
`READ=PASS`
`SCHEMA_VALIDATION=PASS`
`MATCH=PASS`
`BRIDGE_STATE_CONTAINS_VALUE=YES`
`USER_PROMPT_CONTAINS_VALUE=NO`
`GEMINI_INPUT_PROMPT_CONTAINS_VALUE=NO`

Any missing field, `NOT_PROVEN`, `FAIL`, `YES` leak, missing audit, or missing authoritative Bridge record causes the Bridge production gate to fail.

## Persistence isolation

The V26.3 historical persistence test does not request Bridge. Its authoritative historical result therefore remains independent of Bridge diagnostics.

Provider Core, Free Cascade, Secrets, model lists, and canonical persistence/hash contracts are preserved.
