# HOTFIX163.4 — Final Closure Release

This release is a source-level convergence of the two independently validated closure lines.

## Actual code changes
- `main.py`: deterministic Bridge identity per logical Request and an application-owned, provider-free Bridge lifecycle self-test (WRITE → VALIDATE → COMMIT → BARRIER → READ → MATCH).
- `providers.py`: credential-bound runtime candidate resolution restored for actual dispatch/UI snapshots; explicit Free-model configuration remains the only candidate catalog. Legacy `get_model_candidates()` remains available as a configuration projection for historical tests.
- `release_identity.py`: active canonical `VERSION.txt` contract is explicitly audited while HOTFIX117 remains historical and non-active.
- Existing canonical V26.3 persistence, Request/Round identity, Secrets, model lists, and tests are preserved.

## Release rules
No test was modified, deleted, skipped, xfailed, or weakened. No Secret or `*_FREE_MODELS` value was changed.
