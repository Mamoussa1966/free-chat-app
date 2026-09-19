# HOTFIX123.2 — PROVIDER RESPONSE PATH HARDENING

Version: `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`

Built from the complete HOTFIX123.2 artifact. No Secrets, `*_FREE_MODELS`, provider endpoints, or cascade model lists are changed.

Fixes:
- Restores the missing `_render_live_cascade_telemetry()` runtime function introduced by HOTFIX123.2. Its absence raised a `NameError` after provider execution and converted otherwise successful official responses into worker failures.
- Makes Gemini's optional provider-reported model field explicitly initialized, because the official `generateContent` response envelope does not require a top-level `model` field.
- Keeps all cascade attempts inside the same Request ID / Round / Seat execution claim.
- Adds persistent, safe live telemetry rendering as `MODEL → CLASSIFICATION → CASCADE ACTION` without creating any new request or retry path.
- Regression suite: 335 tests passing.

# HOTFIX123 — Production Chat Reliability

Version: `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`

Built directly from the complete previous release release artifact. No Secrets, `*_FREE_MODELS`, provider configuration, or Transactional Bridge prompt-isolation policy is changed.

HOTFIX123 adds a round-scoped `SeatExecutionLedger` enforcing one execution claim per `request_id + round + seat`. Free Cascade attempts remain inside that single provider execution. The runtime also carries a deterministic execution identity for observability and post-request auditing. Existing Streamlit fingerprint protection remains in force before request allocation/provider execution.

Reliability invariants covered by this release:
- one logical Request per seat/round;
- Free Cascade attempts do not create new Requests;
- provider failures remain isolated to the failing seat;
- failure classifications remain bounded and sanitized;
- Streamlit duplicate-submission gate remains before `_run_council()`;
- runtime execution identity is deterministic for the same request/round/seat;
- previous release Transactional Bridge ordering and prompt non-leak remain unchanged.

# HOTFIX123 — Production Readiness / Council Reliability Gate

Version: `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`

## Scope
Built directly from the complete previous release artifact. No Secrets, `*_FREE_MODELS`, provider configuration, Free Cascade configuration, Gemini/DeepSeek configuration, or existing Transactional Bridge prompt-isolation policy is changed.

## Reliability gates
1. Request lifecycle is explicitly audited: `REQUEST_START → ROUTING → PROVIDER_EXECUTION → RESPONSE_VALIDATION → REQUEST_COMMIT`.
2. Provider execution identity records the configured model, actual attempted models, executed model, authoritative one-based cascade position, API mode, status, and failure classification.
3. Cascade position is derived from the actual HTTP-attempt ledger; only the model receiving the HTTP request can become `executed_model`.
4. Transactional Bridge now enforces `WRITE → VALIDATE → COMMIT → BARRIER → READ`; direct READ before BARRIER fails closed.
5. Bridge values remain application-owned and are excluded from provider prompts; audit records remain value-redacted.
6. Provider failures remain failures and are never converted into successful results.
7. Production audit retains request/round/seat/provider/attempt/model/cascade/status/failure/bridge/context/latency metadata without secrets or raw provider payloads.

## Compatibility
The complete previous release file tree is preserved; no files are removed as part of this hotfix.

# HOTFIX123 — Cascade Execution Identity Hardening

Version: `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`

Built directly from the verified previous release release artifact while preserving the complete file tree and existing tests.

## Fixes
- Makes `cascade_position` authoritative from the actual `attempted_models` execution ledger.
- Uses one-based Free Cascade numbering: first actual API attempt = #1.
- Persists `cascade_position` with each successful history message.
- Renders the executed Free Cascade number separately from the configured Free #1 catalog entry.
- Removes the previous UI ambiguity where a successful #3 execution could still be displayed as `Free #1`.
- Adds regression tests proving a three-attempt execution reports `cascade_position = 3` and preserves that identity in history.
- No Secret, `*_FREE_MODELS`, provider catalog, Local Engine, or Paid fallback behavior is changed.

## Preservation
- previous release transactional bridge isolation remains unchanged.
- Prompt non-leak protections remain unchanged.
- Existing test tree is preserved.


## previous release release hardening refresh

- Preserved the complete release tree and the required non-secret `.streamlit/secrets.toml.example`.
- Runtime `.streamlit/secrets.toml` symlinks are excluded from isolated test copies and release ZIPs; arbitrary symlinks remain fail-closed.
- No Secrets, `*_FREE_MODELS`, provider configuration, Free Cascade, Gemini/DeepSeek configuration, or Transactional Bridge behavior is changed.
- Production Core tests and the complete pytest suite are required to pass before packaging.


# HOTFIX123 — Production Gate / Authoritative Cascade Position Reporting

- Built directly from previous release-PRODUCTION-HARDENED-FINAL-FIXED.
- `cascade_position` and `executed_cascade_position` are recomputed from `attempted_models[]` and the actual `executed_model` after the provider HTTP call.
- Free Cascade numbering is strictly one-based: the first actual HTTP attempt is `#1`; `0` is never a valid executed position.
- The explicit transactional bridge diagnostic now receives an application-authenticated runtime attestation after the round completes, preventing provider-generated values from contradicting the authoritative execution ledger.
- Transactional Bridge value remains redacted from prompts; only the proof audit exposes redacted bridge metadata.
- No Secrets, `*_FREE_MODELS`, provider credentials, Local Engine, Paid fallback, Dynamic Model Discovery, or existing bridge policy is changed.
- Full pytest and Production Core Gate must pass before release packaging.

# HOTFIX123 — Runtime Payload Attestation / Immutable Bridge Audit

Version: `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`

Built directly from the complete previous release artifact. The complete file tree is preserved.

## Production Gate closure
- Adds a transient runtime attestation at the exact `requests.post(..., json=payload)` boundary.
- The attestation hashes the exact JSON payload passed to the official HTTP transport and retains the canonical payload only in-process for immediate isolation verification.
- `USER_PROMPT_CONTAINS_VALUE`, `GEMINI_INPUT_PROMPT_CONTAINS_VALUE`, and `BRIDGE_STATE_CONTAINS_VALUE` are now complemented by runtime HTTP payload assertions.
- Adds `RUNTIME_HTTP_PAYLOAD_ATTESTED`, `RUNTIME_HTTP_PAYLOAD_CONTAINS_VALUE`, `RUNTIME_HTTP_PAYLOAD_CONTAINS_BRIDGE_KEY`, and `GEMINI_RECEIVED_SANITIZED_REPRESENTATION_ONLY`.
- Adds a sealed audit hash. The final Production Gate passes only when the current audit equals the sealed canonical audit; post-seal mutation fails the gate.
- Bridge value remains redacted from persistent/UI audit output.
- No Secrets, `*_FREE_MODELS`, provider catalog, Local Engine, Paid fallback, or Dynamic Model Discovery behavior is changed.
- Adds previous release runtime attestation regression tests.

# HOTFIX123.2 — SINGLE-REQUEST DETERMINISM + LIVE CASCADE TELEMETRY HARDENING

- Built directly on HOTFIX123.1; no Secrets or model-list changes.
- One orchestrator execution is permitted per Request ID; a secondary path cannot create a second lifecycle.
- One request/round execution scope is permitted; duplicate round execution is blocked before a second Bridge can be created.
- SeatExecutionLedger remains exactly-once for each Request ID + Round + Seat.
- All Free Cascade attempts remain inside the same Request ID and Round; no retry/cascade attempt allocates a new Request ID.
- Transactional Bridge remains one Bridge ID per request/round scope.
- Live UI telemetry exposes model → classification → cascade action as each provider result becomes available.
- Added explicit regressions for one round/one seat/one request, ten cascade attempts sharing one Request ID, duplicate orchestrator prevention, and duplicate bridge scope prevention.
