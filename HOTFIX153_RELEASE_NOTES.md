# HOTFIX153 — V26.3/V23 CANONICAL COUNTER + AUDIT PREFLIGHT + REGRESSION RESTORATION CLOSURE

- Preserves the complete HOTFIX152 tree; no existing file is removed.
- `canonical_audit_preflight` is a concrete function in `conversation_store.py` with a shared canonical identity-counter contract.
- Canonical counters are derived only from canonical Message/Request/Round identity records: 2 / 2 / 2 for the two-turn proof case.
- Persistence audit separates canonical counts from the six-row UI/projection message list; UI message count is non-authoritative.
- Missing continuation evidence is fail-closed as `status=NOT_PROVEN` with `audit={}`.
- `.streamlit/secrets.toml.example` remains at the exact required path.
- Full regression suite is rerun after the patch.
- Providers, explicit Free Models, Free Cascade, Secrets contract, Request→Round identity, security isolation, and provider execution behavior are outside scope and preserved.
