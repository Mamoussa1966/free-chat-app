# HOTFIX164.12 — Independent Bridge Read Proof and HTTP Boundary

## Confirmed root cause

The strict orchestrator resolved `BRIDGE_RESULT` from the application-owned Bridge store after the Gemini call, then assigned that value to `result["content"]`. That overwrote the provider's actual response and made the exported Gemini `content` appear identical to `bridge_read_value`, even though that equality was created by application code rather than proven to be Gemini's output.

## Surgical correction

- Preserve Gemini's actual provider response in `content`.
- Keep the post-response application-owned read separately in `bridge_read_value`, explicitly tagged with `bridge_read_value_source=APPLICATION_OWNED_BRIDGE_STORE`.
- Record that the target response is not used as Bridge-read proof and that the app-owned source-write/read values match.
- Require those independent source-write/read and response-independence assertions in the strict Bridge security gate.
- Keep runtime HTTP payload attestation mandatory. Missing actual-payload evidence is `NOT_PROVEN`/gate failure, not a pass inferred from prompt text or provider response.
- Update regression expectations to the new security contract and add a fail-closed test for absent HTTP payload attestation.

## Frozen contracts

`VERSION.txt` remains `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`. No Local Engine, Paid fallback, or dynamic model discovery was introduced. The canonical two-message/two-request/two-round lifecycle contract is unchanged.

## Validation

Validation results are recorded only after running the full suite against this source and a fresh ZIP extraction. Passing repository tests do not by themselves establish a deployed live-room security closure; that still requires a new two-message export with independently attested actual HTTP payloads and application-owned Bridge records.
