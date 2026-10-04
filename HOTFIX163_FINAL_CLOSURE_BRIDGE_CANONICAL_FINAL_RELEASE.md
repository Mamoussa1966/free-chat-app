# HOTFIX163 FINAL CLOSURE — Bridge Canonical Evidence

## Scope
This closure is intentionally limited to the final Bridge audit gap. V26.3 Message → Request → Round allocation, persistence, hydration, canonical counters, and request isolation are not changed.

## Bridge closure contract
- Canonical evidence is read from the authoritative V26.3 RequestRecord results.
- Request 1 must contain exactly one Bridge audit record and one Bridge ID.
- Request 2 must contain exactly one Bridge audit record and one Bridge ID.
- Request 1 Bridge ID must differ from Request 2 Bridge ID.
- Each Bridge audit must prove WRITE → VALIDATE → COMMIT → BARRIER → READ.
- Source is exclusively DeepSeek / Seat 7.
- Target is exclusively Gemini / Seat 2.
- `BRIDGE_RESULT` trace records from Seat 7 are never persisted with `target_seat=0`; the target is bound to Seat 2 at trace creation.
- Bridge value remains application-private and is excluded from user/Gemini prompts and runtime HTTP payloads.

## Verification
- Full test suite: `585 passed`.
- The release ZIP is packaged with project files directly at archive root.
- No ZIP is embedded inside the release ZIP.
