# HOTFIX152 — V26.3/V23 CANONICAL RUNTIME RECONSTRUCTION & REGRESSION CLOSURE

- Canonical Audit Preflight hydrates the committed ConversationRecord and rebuilds runtime indexes before V23 final closure.
- Request creation allocates and persists `canonical_round_base` before provider dispatch.
- Message→Request and Request→Round identity remains application-owned and immutable.
- Canonical history reload preserves committed request/round order instead of allowing a narrowed rerun to invert it.
- Continuation status distinguishes PASS / FAIL / NOT_REQUESTED / NOT_PROVEN; missing evidence never becomes PASS.
- Restores legacy `call_seat(..., forbidden_bridge_values=...)` and `record_message(..., request_id=...)` compatibility.
- Restores `.streamlit/secrets.toml.example`.
- Explicit Free-model configuration remains authoritative; no implicit Gemini catalog is introduced.
- No provider configuration, Free Cascade, Local Engine, or Paid fallback changes.
