# HOTFIX117 — Atomic Canonical Historical Lifecycle

Built from HOTFIX116 without deleting source files.

## Scope
- Trace the real Message → Request → Round lifecycle before provider dispatch.
- Add atomic canonical lifecycle checkpoint with fail-closed chain validation.
- Make Round IDs immutable/independent per Request even when round number is 1.
- Preserve canonical history across hydration and strict index rebuild.
- Preserve existing request fingerprint idempotency gate; duplicate logical submissions remain blocked before provider execution.
- Add deterministic canonical history SHA-256 identity checksum to the existing authoritative audit.
- Add canonical chain integrity fields to the existing audit; no separate audit layer is introduced.
- Add positive and negative regression coverage.

## Authority contract
PASS is permitted only when Application-Owned Canonical Runtime State contains the complete Message/Request/Round history and all immutable mappings. Missing canonical transport remains NOT_PROVEN; provider prose, UI text, synthesis prose, and current-only ledgers are not historical authority.

## Provider scope
Provider Core, Free Cascade, Secrets, model lists, and Bridge implementation are outside this fix.
