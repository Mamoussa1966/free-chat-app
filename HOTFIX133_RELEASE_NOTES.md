# HOTFIX133 — AUTHORITATIVE CASCADE ACCOUNTING RECONCILIATION

Built as a narrow accounting correction on top of the HOTFIX132 runtime contract.

## Scope
- No Dispatch Gate changes.
- No Secrets, provider credentials, endpoints, or `*_FREE_MODELS` changes.
- No Free Cascade ordering changes.
- No Local Engine, paid fallback, or automatic model selection.
- Preserves Request ID, Round/Seat execution identity, Transactional Bridge, prompt non-leak, and provider execution contract behavior.

## Fix
- Every provider attempt that crosses the provider execution boundary is marked `execution_started=true`, including failed cascade attempts.
- `TOTAL_CASCADE_ATTEMPTS` is derived only from those authoritative runtime attempt events.
- `PROVIDER_EXECUTION_EVENTS` remains the count of successful provider result events, so it is not confused with attempt count.
- Lifecycle/request-record/UI accounting uses the same runtime attempt evidence.
- Agent-generated prose is never an accounting source.

## Regression invariant
For a run where Gemini executes 3 cascade attempts (2 transient failures + 1 success) and DeepSeek executes 1 successful attempt:
- `TOTAL_CASCADE_ATTEMPTS = 4`
- `PROVIDER_EXECUTION_EVENTS = 2`
- `SUCCESS = 2`
- `NOT_CONFIGURED = 2`
- `DISPATCH_REJECTED = 0`
- one Request ID and one Bridge ID
- DeepSeek Seat 7 Round 1 execution count = 1

## Maintenance principle
This hotfix changes only the broken accounting boundary instead of modifying provider dispatch, model configuration, or unrelated runtime paths.
