# HOTFIX138 — FALSE CONTINUATION REJECTION / FRESH-REQUEST GATE HARDENING

Base: HOTFIX137 (restored HOTFIX134 baseline).

## Root cause fixed
The continuation gate used broad single-word markers such as `continuation`, `continue`, and Arabic `استمر`/`تابع`. Because this gate runs before Request-ID allocation, an ordinary new discussion could be misclassified as a continuation and fail with:

`Continuation rejected: an existing Request ID is required. No Request ID will be generated.`

## Fix
Continuation intent is now recognized only by explicit continuation-control phrases, or by an explicitly supplied Request ID that resolves to a persisted `COMPLETED` REQUEST_RECORD. Ordinary discussion text is not treated as continuation merely because it contains a generic word such as `continuation`.

## Preserved
- Official API only
- No Local Engine
- No Paid fallback
- No automatic model selection
- Explicit Free #1 → Free #10 cascade
- One Request per seat/round
- Transactional Bridge isolation
- Runtime authoritative accounting
- Existing continuation fail-closed behavior when continuation intent is explicit but Request ID is missing/invalid
