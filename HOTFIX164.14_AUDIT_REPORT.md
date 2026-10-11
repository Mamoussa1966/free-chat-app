# HOTFIX164.14 Repository and Artifact Audit

Audit date: 2026-10-11
Repository: `Mamoussa1966/free-chat-app`
Prior artifact reviewed: HOTFIX164.13 HTTP Body Integrity Bridge Closure

## Findings in HOTFIX164.13

1. `VERSION.txt` correctly retained the frozen Provider identity `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`.
2. The HOTFIX164.13 manifest's listed SHA-256 digests were independently recomputed from the artifact and matched.
3. `providers.py` still exposed `CURRENT_HOTFIX_RELEASE_VERSION = HOTFIX164.10 ...`; the UI banner therefore contradicted the HOTFIX164.13 manifest and release note.
4. The provider adapter prepared a `requests.PreparedRequest`, calculated SHA-256 and byte length from its body bytes, and passed those bytes using `data=...`. `main.py` recomputed SHA-256 from the attested body and strict live mode required the prepared-request boundary markers. The existing negative regression test rejects a fabricated digest.
5. The published Streamlit app could not be fetched from this verification environment (DNS/network resolution failed). No fresh deployed two-message Bridge export was available, so deployment identity and live final Bridge closure remain NOT PROVEN.

## HOTFIX164.14 corrections

- The visible runtime release label is now `HOTFIX164.14 — HTTP BODY INTEGRITY AND RELEASE IDENTITY CLOSURE`, with a regression test tying it to this release manifest.
- Provider transport continues to send the same pre-prepared body bytes as `data=prepared_body`. The compatibility `json=payload` keyword is retained because existing provider adapter tests depend on that call shape; the exact bytes and their digest are asserted against the `data` argument. This proves the body supplied at the application's `requests.post` call boundary, not packet capture beyond the TLS/network stack.
- The frozen `VERSION.txt` identity is unchanged. No Local Engine, paid fallback, or dynamic model discovery was enabled.
- Existing tests are preserved; no tests were skipped or marked xfail.

## Local verification

- Full local suite: 615 passed, 0 failed.
- Fresh ZIP extraction and complete suite: 615 passed, 0 failed.
- ZIP root layout: `main.py`, `providers.py`, `conversation_store.py`, `VERSION.txt`, manifest, and `tests/` are at the archive root.
- Nested ZIPs: none.
- Actual secrets file: not packaged; `.streamlit/secrets.toml.example` retained.
- Release manifest file hashes for listed files: checked during packaging.

## Remaining deployed-live acceptance gate

To declare full final closure, deploy HOTFIX164.14 and provide a fresh export from that deployed room containing exactly two user messages / two canonical Requests / two canonical Rounds. For each strict live Bridge record, inspect the application-owned event chain `SOURCE_EXECUTION → WRITE → VALIDATE → COMMIT → BARRIER → TARGET_DISPATCH → TARGET_RESPONSE → READ → MATCH`, a unique per-request Bridge ID hash, verified prepared-body hash/length, explicit absence of Bridge value/key/ID/request ID/canonical round ID from the Gemini prompt and actual prepared HTTP body, and an application-owned read that is not copied from Gemini's response. Missing or contradictory evidence must remain NOT_PROVEN/FAIL.

This package closes the locally testable release-label and body-integrity regression. It does not claim that the published app has already deployed HOTFIX164.14 or that live final Bridge closure is proven.
