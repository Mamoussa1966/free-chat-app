# HOTFIX116 — Production Readiness / Council Reliability Gate

Version: `V22.1-HOTFIX116-PRODUCTION-HARDENED`

## Scope
Built directly from the complete HOTFIX116 artifact. No Secrets, `*_FREE_MODELS`, provider configuration, Free Cascade configuration, Gemini/DeepSeek configuration, or existing Transactional Bridge prompt-isolation policy is changed.

## Reliability gates
1. Request lifecycle is explicitly audited: `REQUEST_START → ROUTING → PROVIDER_EXECUTION → RESPONSE_VALIDATION → REQUEST_COMMIT`.
2. Provider execution identity records the configured model, actual attempted models, executed model, authoritative one-based cascade position, API mode, status, and failure classification.
3. Cascade position is derived from the actual HTTP-attempt ledger; only the model receiving the HTTP request can become `executed_model`.
4. Transactional Bridge now enforces `WRITE → VALIDATE → COMMIT → BARRIER → READ`; direct READ before BARRIER fails closed.
5. Bridge values remain application-owned and are excluded from provider prompts; audit records remain value-redacted.
6. Provider failures remain failures and are never converted into successful results.
7. Production audit retains request/round/seat/provider/attempt/model/cascade/status/failure/bridge/context/latency metadata without secrets or raw provider payloads.

## Compatibility
The complete HOTFIX116 file tree is preserved; no files are removed as part of this hotfix.

# HOTFIX116 — Cascade Execution Identity Hardening

Version: `V22.1-HOTFIX116-PRODUCTION-HARDENED`

Built directly from the verified HOTFIX116 release artifact while preserving the complete file tree and existing tests.

## Fixes
- Makes `cascade_position` authoritative from the actual `attempted_models` execution ledger.
- Uses one-based Free Cascade numbering: first actual API attempt = #1.
- Persists `cascade_position` with each successful history message.
- Renders the executed Free Cascade number separately from the configured Free #1 catalog entry.
- Removes the previous UI ambiguity where a successful #3 execution could still be displayed as `Free #1`.
- Adds regression tests proving a three-attempt execution reports `cascade_position = 3` and preserves that identity in history.
- No Secret, `*_FREE_MODELS`, provider catalog, Local Engine, or Paid fallback behavior is changed.

## Preservation
- HOTFIX116 transactional bridge isolation remains unchanged.
- Prompt non-leak protections remain unchanged.
- Existing test tree is preserved.


## HOTFIX116 release hardening refresh

- Preserved the complete release tree and the required non-secret `.streamlit/secrets.toml.example`.
- Runtime `.streamlit/secrets.toml` symlinks are excluded from isolated test copies and release ZIPs; arbitrary symlinks remain fail-closed.
- No Secrets, `*_FREE_MODELS`, provider configuration, Free Cascade, Gemini/DeepSeek configuration, or Transactional Bridge behavior is changed.
- Production Core tests and the complete pytest suite are required to pass before packaging.


# HOTFIX116 — Production Gate / Authoritative Cascade Position Reporting

- Built directly from HOTFIX116-PRODUCTION-HARDENED-FINAL-FIXED.
- `cascade_position` and `executed_cascade_position` are recomputed from `attempted_models[]` and the actual `executed_model` after the provider HTTP call.
- Free Cascade numbering is strictly one-based: the first actual HTTP attempt is `#1`; `0` is never a valid executed position.
- The explicit transactional bridge diagnostic now receives an application-authenticated runtime attestation after the round completes, preventing provider-generated values from contradicting the authoritative execution ledger.
- Transactional Bridge value remains redacted from prompts; only the proof audit exposes redacted bridge metadata.
- No Secrets, `*_FREE_MODELS`, provider credentials, Local Engine, Paid fallback, Dynamic Model Discovery, or existing bridge policy is changed.
- Full pytest and Production Core Gate must pass before release packaging.
