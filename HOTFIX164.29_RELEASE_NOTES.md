# HOTFIX164.29 — Independent HTTP-Attested Bridge Closure Gate

## Actual code changes

1. The deployed release label now identifies `HOTFIX164.29` while `VERSION.txt` and the provider core remain exactly `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`.
2. The read-only forensic report now exports the application release identity and generation time, plus a redacted per-target attestation envelope. It contains the SHA-256 and byte count for the exact prepared HTTP body, prepared-request and transport-boundary checks, Request/Round/Gemini/response binding statuses, Bridge phase order, seat identity statuses, and explicit leak checks. It does not export raw body bytes, prompts, Bridge values, or raw Bridge IDs.
3. `HOTFIX164.29_INDEPENDENT_CLOSURE_GATE.py` independently validates the fresh app report, the two canonical request/round chains, strict Bridge evidence, the safe HTTP attestation envelope, the release manifest, the ZIP contents, the frozen provider identity, and the detached SHA-256 sidecar.
4. The new GitHub Actions workflow runs the full offline test/build round-trip first and marks final closure as proven only when the committed fresh report passes the independent checker against the exact candidate ZIP. Missing or stale evidence returns `NOT_PROVEN` and blocks publication.
5. New regression tests verify that the checker accepts a structurally complete test fixture, rejects the old report shape, rejects a missing payload attestation, and rejects a checksum mismatch. These tests validate checker logic only; they are not presented as live Bridge proof.

## Preserved constraints

- `VERSION.txt` stays exactly `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`.
- No local engine, paid fallback, dynamic model discovery, or additional provider API calls are added by the gate.
- The audit remains read-only and does not allocate Requests, Rounds, or Bridge transactions.
- Provider prose remains non-authoritative.

## Live closure status

**LIVE FINAL CLOSURE: NOT_PROVEN until a fresh HOTFIX164.29 deployment produces new Run A and Run B evidence and that exact report passes the independent gate.**

The previous HOTFIX164.28 report cannot close this release because it does not contain the HOTFIX164.29 release binding or the new per-target HTTP attestation envelope.
