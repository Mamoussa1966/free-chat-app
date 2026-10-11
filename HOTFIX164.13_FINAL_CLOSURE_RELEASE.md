# HOTFIX164.13 — HTTP Body Integrity Gate and Bridge Closure Hardening

## Scope

HOTFIX164.13 hardens the Bridge payload attestation boundary and preserves the independent separation between the Gemini response content and the application-owned Bridge read.

## Security changes

- Build a `requests.PreparedRequest` and pass its exact prepared body bytes to the HTTP transport.
- Compute the payload SHA-256 and byte length from those exact bytes.
- Carry explicit `transport_boundary` and `prepared_request_verified` metadata from the provider transport.
- Validate the supplied SHA-256 against the stored body before the application audit can count the attestation.
- In strict live Bridge mode, require both a matching digest and the expected prepared-request boundary metadata.
- Fail closed when the digest is fabricated, malformed, mismatched, or missing.
- Add regression coverage for synthetic hashes and for the actual prepared body bytes passed to `requests.post`.
- Preserve provider identity in `VERSION.txt`; no Local Engine, Paid fallback, or dynamic model discovery was introduced.

## Validation boundary

A passing repository suite and fresh ZIP round-trip prove local regression and packaging behavior. They do **not** prove that a deployed live room used this archive or that a two-message live export has been independently inspected. Therefore the release artifact is **CODE/REPOSITORY CLOSURE VERIFIED; LIVE FINAL CLOSURE NOT PROVEN** until a new two-message live-room export is examined.
