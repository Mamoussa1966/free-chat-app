# AI Council V22.1 — HOTFIX13

Built from the HOTFIX12 source while preserving the existing test-suite surface and adding explicit execution identity and result uniqueness invariants.

## Invariants
- `GEMINI_FREE_MODELS` → ordered `model_candidates` remains explicit and Secrets-first.
- The router's selected model is recorded as `executed_model` immediately at the official call boundary.
- Successful `model`, `executed_model`, and the last `attempted_models` entry must agree.
- Round, History, and Diagnostics render the same authoritative execution identity.
- Exactly one persisted result is allowed for `(request_id, round, seat)`.
- Candidate #2 cannot be skipped when #1 fails with a cascade-eligible error.
- No Local Engine and no paid fallback.
- `get_gemini_transcriber_model` remains part of the `main.py` ↔ `providers.py` import contract.
