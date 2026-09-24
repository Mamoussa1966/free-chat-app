# HOTFIX147 — V23 Security + Regression Closure

Additive closure patch above HOTFIX146. Independent fixes only:

1. **Security NO_RAW** — the security gate no longer treats the literal field name `raw_provider_payload` as retained provider data. It fails only when a forbidden raw-payload field contains a non-empty value, including nested records.
2. **Regression Core** — restores the HOTFIX130 compatibility APIs `_authoritative_ui_projection` and `_format_authoritative_counter_summary`. The projection reads persisted request metrics/results, never the six-row UI message projection, agent prose, or latest-request projection.
3. **Release preservation** — HOTFIX146 already contains `.streamlit/secrets.toml.example`; it is retained unchanged. No provider credentials, model lists, or canonical persistence semantics are changed.

Preserved contracts:
- HOTFIX123.2 single-request determinism and live cascade telemetry.
- HOTFIX129 semantic state counters.
- HOTFIX130 authoritative counter semantics.
- V26.3 canonical persistence and Round identity.
- No Local Engine, no Paid fallback, no automatic model selection.

Validation target: HOTFIX146 full suite must remain green, plus HOTFIX147 security/regression tests.
