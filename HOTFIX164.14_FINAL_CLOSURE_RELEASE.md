# HOTFIX164.14 — HTTP Body Integrity and Release Identity Closure

## Scope

HOTFIX164.14 is a narrow corrective release over HOTFIX164.13. It retains the frozen Provider identity in `VERSION.txt`, the official API-only architecture, Free-model allowlists, and the application-owned Bridge evidence store.

## Corrections

- Align the runtime-visible `CURRENT_HOTFIX_RELEASE_VERSION` banner with this release identifier. This removes the HOTFIX164.10 banner versus HOTFIX164.13/164.14 release metadata conflict without changing `VERSION.txt`.
- Preserve the established provider adapter call signature, while explicitly documenting that the non-empty `data=prepared_body` bytes are the transmitted body under `requests` semantics. The integrity regression confirms the data bytes, digest, byte count, and decoded payload agree; the compatibility `json=payload` keyword remains for existing adapter tests/contracts.
- Strengthen regression coverage to assert the request passes those exact prepared bytes as `data`, the recorded digest and byte count match the exact body, and the runtime release label matches the release manifest.
- Retain negative regression tests proving fabricated/missing/mismatched payload hashes fail closed.

## Verification boundary

The release ZIP is accepted only after the complete local test suite, a fresh extraction, and a second complete test run pass. `VERSION.txt` remains exactly `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`.

A live two-message room export from the deployed Streamlit service was not available to this build-time verification. Therefore the code/package closure can be verified locally, but deployed live final Bridge closure remains **NOT PROVEN** until the deployed room identity and application-owned Bridge evidence are freshly exported and inspected.
