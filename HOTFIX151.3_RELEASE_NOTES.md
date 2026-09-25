# HOTFIX151.3 — FULL AUDIT ACTION BAR / TRUE PAYLOAD COPY

## Scope
UI-only hardening for the V23 full-audit action surface.

## Contract
Exactly one adjacent Action Bar contains:

1. ▶️ Run full V23 platform audit
2. 📋 Copy Full V23 Audit Report
3. 💾 Download Full V23 Audit JSON

## Copy semantics
The Copy action serializes the complete application-owned `audit_export` payload directly into the browser-side clipboard payload. It does not read, select, or depend on the visible `st.code` report viewport.

## Download semantics
Download uses the same deterministic serialized `audit_export_text` produced from the complete payload.

## Runtime semantics
No provider, cascade, persistence, canonical counter, identity, bridge, security, or audit computation semantics are changed by this hotfix.

## Regression protection
The HOTFIX151.2 baseline is preserved; only the intended `main.py` UI block and HOTFIX151.3 release/test artifacts are added/updated.
