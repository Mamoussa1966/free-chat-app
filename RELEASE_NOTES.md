# Current release — Timeout-only finalization

Version: `V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX71-FINAL`

## Scope

Built directly from the existing current project tree. No provider, seat, cascade-order, credential, model-list, architecture, Local Engine, paid-fallback, or automatic-selection changes are introduced.

## Unlimited response-time contract

- The previous 2.0-second per-attempt HTTP timeout has been removed.
- The previous 2.0-second per-seat wall-clock budget has been removed.
- Official provider requests now use no artificial transport timeout (`requests` timeout is `None`).
- The council no longer aborts a provider merely because it exceeded 2 seconds.
- Hidden HTTP retries remain disabled; the explicit Free-model cascade remains the only sequential failover mechanism.
- No provider, model list, seat numbering, credentials, Local Engine, paid fallback, or automatic model selection changes were introduced.

## Latency semantics

There is now no application-imposed 2-second cutoff. Actual response time remains dependent on network conditions, provider-side processing, rate limits, and the configured cascade. Removing the timeout cannot force an external provider to respond faster; it removes the application's artificial cutoff so a valid official request can complete.

## No-timeout public finalization
1. Preserved the runtime timeout behavior.
2. Converted public timeout outcomes to neutral `NO_RESPONSE` status/classification.
3. Suppressed failed-attempt timeout expanders for pure latency cutoffs.
4. Added regression tests proving `TIMEOUT` does not leak into public result rendering.
5. No provider model catalog, seat numbering, credentials, cascade order, or architecture changed.


# HOTFIX71 — DeepSeek cascade progression regression hardening

- Built directly from the immediately preceding final release; no unrelated provider or UI behavior changed.
- Preserves unlimited provider/cascade latency: no 2-second or 45-second artificial timeout restored.
- Restores `MAX_OUTPUT_TOKENS` default to 1200, matching the previously verified 1200-token behavior.
- Adds a direct regression proving `ProviderError(error_class="API_ERROR")` on DeepSeek candidate #1 advances to candidate #2.
- Preserves terminal identity-mismatch behavior; no automatic model selection, Local Engine, or paid fallback.
