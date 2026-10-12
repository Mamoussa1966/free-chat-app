# HOTFIX164.15 — Strict Bridge Target-Seat Identity Closure

## Root cause
Strict live Bridge proof previously validated event order and statuses but did not require the COMMIT event to bind to Gemini seat 2. `commit(None)` could therefore record `target_seat=0` and later events could still be labelled as Gemini phases.

## Changes
- Strict live commit now rejects missing, wrong-provider, or wrong-slot target identity before mutating terminal state.
- Orchestration validates the Gemini target seat before attempting commit; invalid target identity aborts the transaction.
- Application-owned strict evidence validation now requires source phases to identify DeepSeek seat 7, COMMIT/BARRIER to bind target seat 2, and target phases to identify seat 2. Missing identity fails closed.
- Added focused regression tests for missing target, wrong target, and valid Gemini seat 2.

## Preserved contracts
- `VERSION.txt` remains `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`.
- Official API only; no local engine, paid fallback, or dynamic model discovery.
- Existing tests are retained; fixture updates only add explicit seat identity required by the strengthened evidence contract.

## Validation boundary
Local pytest and ZIP round-trip results are recorded in the delivery response. A live two-message Streamlit run requires the deployed app and real official API credentials and is not claimed from local tests.
