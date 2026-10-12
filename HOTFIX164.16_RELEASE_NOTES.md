# HOTFIX164.16 — Bridge Runtime Evidence Export Closure

## Scope
A narrow regression release above HOTFIX164.15. It fixes the Python 3.11 f-string syntax error in the Conversation/Session caption and preserves sanitized control-plane leak attestations in exported Bridge evidence. V26.3 identity allocation and canonical counters are untouched.

## Changes
- Replace double-quoted literals inside the existing f-string expressions with single-quoted literals; display behavior is unchanged.
- Preserve redacted control-plane identity statuses in the application-owned Bridge runtime export.
- Add regressions proving boundary statuses survive export and observed YES leaks remain visible.
- Keep raw Bridge IDs redacted and exclude raw Bridge values and HTTP request bodies.

## Acceptance boundary
Full-suite and fresh ZIP round-trip status must come from build_release.py. This local package does not claim that GitHub Actions passed or that a live two-message room closure occurred; live closure needs the deployed Streamlit runtime and official API credentials.
