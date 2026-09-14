# HOTFIX65 — Timeout-only finalization

Version: `V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX65-FINAL`

## Scope

Built directly from the existing HOTFIX65 project tree. No provider, seat, cascade-order, credential, model-list, architecture, Local Engine, paid-fallback, or automatic-selection changes are introduced.

## Timeout contract

- Every individual provider cascade attempt is hard-capped at **2.0 seconds**.
- The explicit Free-model cascade remains the only sequential failover mechanism.
- Hidden HTTP retries remain disabled for the cascade path.
- A timed-out model proceeds to the next explicitly configured model when the remaining seat budget permits.
- Gemini and DeepSeek use the same two-second per-attempt contract.
- Existing Gemini, Claude, Grok, Kimi, DeepSeek, dynamic 20-seat, human seat 6, and diagnostics behavior is preserved.
- No credentials are packaged.

## Important latency semantics

The 2.0-second value is an upper bound for an individual HTTP attempt, not a guarantee that a complete Streamlit round or provider response will render in 2.0 seconds. Network scheduling, Streamlit reruns, provider-side processing, and subsequent cascade attempts can make the displayed total round time larger.
