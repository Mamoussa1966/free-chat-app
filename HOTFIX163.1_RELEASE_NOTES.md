# HOTFIX163.1 — Repository Canonical State Boundary Fix

- Adds a local, read-only HOTFIX163.1 repository diagnostic path.
- The diagnostic is intercepted before Message/Request/Round allocation.
- It cannot dispatch providers, Cascade, Synthesis, Commit, Relink, or live hydration mutation.
- Canonical counters remain derived from application-owned canonical identity records.
- Hydration probing is performed only on deep copies.
- No tests were modified.
