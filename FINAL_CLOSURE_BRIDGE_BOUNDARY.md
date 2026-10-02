# HOTFIX163.1 — Final Bridge Boundary Closure

This release preserves the V26.3 canonical Message→Request→Round allocation and adds only boundary hardening:

- Production-facing model snapshots are credential-bound: no credential means no dispatch candidates.
- Transactional Bridge IDs are deterministic per logical Request, preventing a secondary bridge identity for the same Request.
- An application-owned provider-free bridge boundary probe proves WRITE → VALIDATE → COMMIT → BARRIER → READ and verifies that the bridge key/value remain outside the Gemini prompt and HTTP payload.
- `VERSION.txt` remains the canonical provider release version. HOTFIX117's historical version is metadata only and cannot become active.
