# V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX67-FINAL

- Built from the immediately preceding timeout-focused release baseline.
- Preserves the complete existing project tree, Free Cascade ordering, provider seats, and user seat 6 / DeepSeek seat 7 architecture.
- Keeps the individual cascade-model HTTP timeout at 2 seconds.
- Expands only the per-seat cascade execution window to 20 seconds, allowing the explicit Free cascade to continue through configured models instead of terminating after the first 2-second attempt.
- No additional HTTP retries are introduced.
- TIMEOUT remains an internal transport diagnostic only. The visible terminal classification for an exhausted no-response cascade is NO_RESPONSE_AFTER_CASCADE, so a missing provider response is not presented as the cause being "TIMEOUT".
- No Local Engine, no paid fallback, and no automatic model selection.

# HOTFIX67 — No-response / timeout separation
- Built directly from HOTFIX67 multi-agent final.
- Preserves all provider adapters, model cascades, room seats, Secrets contract, and 20-seat architecture.
- Keeps transport TIMEOUT as an internal diagnostic classification.
- Separates the public UI wording from the transport timeout so a provider that does not complete an attempt is not described as deliberately "no response because of timeout".
- No Local Engine, paid fallback, automatic model selection, model deletion, seat renumbering, or credential changes.
