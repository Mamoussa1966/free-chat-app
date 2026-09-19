# HOTFIX133 — AUTHORITATIVE CASCADE ACCOUNTING RECONCILIATION

Built directly from the verified HOTFIX132 artifact. This is a narrow provider-attempt accounting fix.

## Root cause fixed
HOTFIX132 correctly opened the provider dispatch boundary, but failed cascade attempts were marked `execution_started=true` in the canonical attempt diagnostics and that marker was dropped when `attempt_telemetry` was projected. Consequently the authoritative runtime event list retained only successful attempts, undercounting cascade attempts and making later accounting inconsistent.

## Fix
- Preserve `execution_started` when projecting canonical attempt diagnostics into safe runtime telemetry.
- Every actual provider attempt, including failed cascade attempts, now remains eligible for the authoritative runtime execution-event projection.
- `TOTAL_CASCADE_ATTEMPTS` is derived from those runtime execution events only.
- `PROVIDER_EXECUTION_EVENTS` remains the lifecycle `PROVIDER_RESULT` event count; it is not conflated with attempt count.
- No Dispatch Gate, Secrets, credentials, endpoints, model lists, cascade ordering, Bridge implementation, or prose-isolation logic changed.

## Expected regression
For Gemini attempts #1/#2 transient failure + #3 success and DeepSeek #1 success:
`TOTAL_CASCADE_ATTEMPTS=4`, `PROVIDER_EXECUTION_EVENTS=2`, `SUCCESS=2`, `DISPATCH_REJECTED=0`, `NOT_CONFIGURED=2`.

## Preservation
The complete HOTFIX132 file tree is retained; no baseline files are removed.
