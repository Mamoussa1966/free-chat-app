# HOTFIX124 — BRIDGE-ONLY CORRECTIVE RELEASE

HOTFIX124 is an additive Bridge/Security corrective release above the frozen deployed identity.
It does **not** change Provider Core, Free Cascade model lists, credentials, persistence/hash logic,
or the frozen HOTFIX123 deployed-release identity.

## Corrective contract

The application-owned Bridge test path is now explicit and exclusive:

Application creates canary → WRITE → VALIDATE → COMMIT → BARRIER → application READ → MATCH.

Provider prose is untrusted presentation data and cannot overwrite an application-owned Bridge record.
The canary is never copied into the user prompt, Gemini input prompt, or official Gemini HTTP payload.

## Fail-closed audit

When no canary exists, isolation fields are `NOT_PROVEN`, never an invented `YES`/`NO`.

## Publication regression gate

The release gate requires all ten displayed security invariants to hold (the user's seven transaction
checks plus Bridge-state and both prompt-boundary checks):

- WRITE = PASS
- VALIDATE = PASS
- COMMIT = PASS
- BARRIER = PASS
- READ = PASS
- SCHEMA_VALIDATION = PASS
- MATCH = PASS
- BRIDGE_STATE_CONTAINS_VALUE = YES
- USER_PROMPT_CONTAINS_VALUE = NO
- GEMINI_INPUT_PROMPT_CONTAINS_VALUE = NO

Any mismatch is a hard FAIL; HOTFIX124 is not production-ready until the gate is PASS.
