# HOTFIX163.1 — FINAL CLOSURE BRIDGE BOUNDARY HARDENED

## Verified code changes

1. `providers.py`
   - Added a credential-bound dispatch candidate resolver.
   - The application-facing `capture_model_candidates()` now uses the strict resolver.
   - Contract: no provider credential => no dispatch candidates; explicit Free-model configuration alone never grants runtime eligibility.

2. `main.py`
   - Transactional Bridge identity is deterministic per logical Request, preventing a second Bridge ID from being minted for the same Request.
   - Added an application-owned, provider-free HOTFIX163.1 Bridge boundary self-test that verifies WRITE → VALIDATE → COMMIT → BARRIER → READ and prompt/HTTP-payload redaction.

3. `release_identity.py`
   - Added an explicit canonical provider version contract.
   - HOTFIX117's historical version is recorded as historical metadata and cannot become the active `VERSION.txt` release identity.

## Preserved contracts

- `VERSION.txt` remains `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`.
- V26.3 canonical Message → Request → Round allocation is unchanged.
- No test files were modified.
- No Free-model lists were changed.
- No Local Engine, paid fallback, or dynamic model discovery was added.

## Verification performed

- Full source-tree test suite: `579 passed`.
- Credential-free Gemini dispatch candidate probe: `[]`.
- Bridge boundary self-test: `PASS`, provider dispatch calls `0`, request creation `0`, round creation `0`.
- Version contract audit: `PASS`.
- Required files present at archive root: `main.py`, `conversation_store.py`, `tests/`, `.streamlit/secrets.toml.example`.
- Final ZIP round-trip is required to be verified from the extracted archive before release.
