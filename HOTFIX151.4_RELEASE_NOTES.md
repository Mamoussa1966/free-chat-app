# HOTFIX151.4 — SINGLE V23 AUDIT HEADING / ACTION BAR DEDUPLICATION

## Root cause
The V23 audit used the expander label as a heading and also rendered an identical inner `st.subheader`. This produced two visible V23 audit headings: the upper expander label without buttons and a second heading above the action bar.

## Fix
The redundant inner V23 `st.subheader` is removed. The expander label is now the single authoritative visible heading, and the three controls remain directly underneath it in one adjacent Action Bar:

- ▶️ Run full V23 platform audit
- 📋 Copy Full V23 Audit Report
- 💾 Download Full V23 Audit JSON

## Copy contract
HOTFIX151.3 payload-copy semantics are unchanged: Copy serializes the complete application-owned `audit_export` payload directly, not the visible report viewport.

## Scope
UI-only. No provider, cascade, persistence, canonical counter, Request/Round identity, bridge, security, or audit computation semantics are changed.
