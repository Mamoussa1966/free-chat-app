# HOTFIX151.1 — MOBILE FULL AUDIT COPY UX

Narrow UX correction on top of HOTFIX151.

## Scope
- Adds a dedicated in-page **Copy Full Audit Report** browser control for long V23 audit exports.
- Keeps the existing JSON download button as fallback.
- Does not change V23 audit computation, canonical persistence, counters, Request→Round identity, providers, models, Secrets, cascade, seats, Bridge, or synthesis.
- No existing HOTFIX151 files are removed.

## Verification
- `main.py` syntax compilation passes.
- Baseline preservation is verified by packaging from the complete HOTFIX151 archive.
