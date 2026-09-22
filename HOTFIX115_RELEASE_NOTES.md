# HOTFIX115 — CANONICAL HISTORICAL CONTRACT / HOTFIX112-STYLE ROLLBACK HARDENING

This release preserves the complete source tree and Provider Core/Free Cascade/Secrets/Model Lists/Bridge/Security.

## Scope
- Historical authority remains the application-owned canonical ConversationRecord.
- Authoritative audit performs HYDRATE → REBUILD INDEXES → AUDIT.
- REBUILD strictly replaces runtime compatibility indexes from canonical history.
- No historical fallback to current Request, request_records, latest Round, or agent prose.
- `reconcile_request()` receives the same Streamlit session transport explicitly; no undefined `session_state` path remains.
- Round lifecycle commits receive session transport so Message → Request → Round history survives reruns.

## Contract
- HISTORICAL_MESSAGE_COUNT = 2
- HISTORICAL_REQUEST_COUNT = 2
- HISTORICAL_ROUND_COUNT = 2
- independent ROUND_ID values
- Message 1 → Request 1 PASS
- Message 2 → Request 2 PASS
- Request 1 → Round 1 PASS
- Request 2 → Round 1 PASS
- PREVIOUS_REQUEST_REEXECUTED = NO
- TWO_MESSAGE_ISOLATION = PASS

No provider execution policy or credential/model configuration was changed.
