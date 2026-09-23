# HOTFIX122 — CANONICAL HISTORY HASH VERIFICATION

Purpose: close the remaining HOTFIX121 persistence proof gap where `canonical_transport_hash_matches` could report `NOT_PROVEN` even though the canonical store contained a committed history hash.

Root-cause fix:
- Treat Streamlit SessionState as a Mapping-like transport, not only as a plain `dict`.
- Preserve the committed `history_hash` from `V26_3_CANONICAL_CONVERSATION_STORE` during snapshot hydration.
- Historical Audit compares the recomputed deterministic hash of the hydrated canonical Message/Request/Round snapshot against the committed canonical-store hash.
- The field is `true` only on an exact digest match; a deliberately corrupted stored digest yields `false`. No agent prose, current-request ledger, or fallback source is used.

Scope boundary:
- Provider Core, Free Cascade, Secrets, Model Lists, and Bridge behavior are unchanged.
- Existing canonical history is preserved; no deletion or narrowing of the authoritative store is introduced.

Validation:
- Positive Mapping/Streamlit-like transport hash test.
- Negative tampered-hash test.
- Full targeted test suite, compile check, and ZIP integrity check performed before release.
