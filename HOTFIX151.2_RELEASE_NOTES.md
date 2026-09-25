# HOTFIX151.2 — FULL AUDIT ACTION BAR / TRUE FULL-REPORT COPY

## Scope
A UI-only hardening layer above HOTFIX151. The audit execution, audit payload construction, canonical persistence, counters, request/round identity, providers, cascade, bridge, synthesis, and security semantics are unchanged.

## Changes
- Places `Run full V23 platform audit`, `Copy Full V23 Audit Report`, and `Download Full V23 Audit JSON` in one adjacent action bar.
- Copy action copies the complete application-owned `audit_export_text` payload directly, not the visible portion of `st.code`.
- Uses Clipboard API when available and a textarea `execCommand("copy")` fallback for mobile/browser compatibility.
- Download action uses the exact same `audit_export_text` payload as the copy action.
- The visible JSON block remains a diagnostic/view surface only; it is not the source of truth for copy/download.

## Non-goals
No changes to provider configuration, model lists, secrets, Free Cascade, request lifecycle, canonical counters, identity binding, Bridge, synthesis, or audit logic.
