# HOTFIX159 — V26.3 CANONICAL ROUND IDENTITY / PERSISTENCE CLOSURE

Final closure scope:

- Request creation allocates `canonical_round_base` from the next canonical Round ordinal.
- First Request starts at Round 1; second Request starts at Round 2.
- Runtime round calculation uses `canonical_round_base + local_round_no - 1`.
- Canonical RoundRecord materializes `record_type=CANONICAL_ROUND_RECORD`, `round_number`, `ordinal`, and `canonical_round_base`.
- Rehydration is authoritative from `V26_3_CANONICAL_CONVERSATION_STORE` and reconstructs the full canonical chain before runtime indexes are rebuilt.
- A narrow migration repairs the known complete 2→3 one-round-per-request drift to 1→2 using Request creation order only; malformed mappings are not silently repaired.
- UI projections, provider results, completion order, and agent prose are never used to allocate historical Round identity.
- Canonical persistence remains the single source of truth.
- Existing files are preserved; `.streamlit/secrets.toml.example` remains present.

Target invariant for the two-message contract:

`Message 1 → Request 1 → Round 1`

`Message 2 → Request 2 → Round 2`

`canonical_message_count = 2`

`canonical_request_count = 2`

`canonical_round_count = 2`

`canonical_round_sequence_base = 1`

`source_rounds = [1, 2]`

Validation performed on the release tree: **544 pytest tests passed**.
