# AI Council V22.1 — HOTFIX13

## Model execution identity and strict cascade

- Enforces authoritative `executed_model` identity for successful official API calls.
- Persists `executed_model` with each successful chat message.
- Displays the executed model and cascade attempts only after identity validation.
- Adds regression tests proving strict `#1 → #2 → #3` ordering with no skipped candidate.
- Adds tests proving first-success stops the cascade and terminal failures do not jump forward.
- Fixes provider-call argument mismatch in the round and diagnostic worker paths.
- Free-only cascade remains limited to models explicitly configured in `*_FREE_MODELS`; no paid/local fallback is introduced.
