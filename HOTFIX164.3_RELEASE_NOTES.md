# HOTFIX164.3 — Bridge Runtime Evidence Closure

Scope is intentionally limited to the Transactional Bridge evidence boundary; V26.3 canonical persistence and the frozen provider contract are preserved.

## Runtime closure contract
For each logical Request, the application records exactly one Request-scoped Bridge evidence ledger with the ordered phases:

`SOURCE_EXECUTION → WRITE → VALIDATE → COMMIT → BARRIER → TARGET_DISPATCH → TARGET_RESPONSE → READ → MATCH`

The final Bridge security gate derives its strict closure decision from this Application-Owned record plus runtime HTTP payload attestation. Agent prose, UI order, completion order, latest-request projections, and provider-generated counters are not authoritative.

## P0 closure changes
- Source execution proof requires a matching persisted runtime execution event for the exact Request/Round/Seat.
- Live Bridge commit requires `PROVIDER_UNTRUSTED_DATA` provenance and the proven source execution.
- Gemini target dispatch is suppressed until Bridge `COMMIT` and `BARRIER` are complete.
- Target response is recorded before the application-owned READ.
- MATCH is recorded by the application after READ; no provider prose establishes it.
- Strict live Bridge audit fails closed when the ordered runtime evidence, HTTP payload attestation, or sanitation proof is missing.

## P1 preservation
- Canonical Message/Request/Round persistence remains unchanged.
- Existing provider-free Bridge compatibility tests remain application-owned and separate from live-source provenance.
- No Dynamic Model Discovery, Local Engine, Paid fallback, or implicit provider/model changes were introduced.
