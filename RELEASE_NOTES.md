# V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX66-FINAL

- Built from the immediately preceding timeout-focused release baseline.
- Preserves the complete existing project tree, Free Cascade ordering, provider seats, and user seat 6 / DeepSeek seat 7 architecture.
- Keeps the individual cascade-model HTTP timeout at 2 seconds.
- Expands only the per-seat cascade execution window to 20 seconds, allowing the explicit Free cascade to continue through configured models instead of terminating after the first 2-second attempt.
- No additional HTTP retries are introduced.
- TIMEOUT remains an internal transport diagnostic only. The visible terminal classification for an exhausted no-response cascade is NO_RESPONSE_AFTER_CASCADE, so a missing provider response is not presented as the cause being "TIMEOUT".
- No Local Engine, no paid fallback, and no automatic model selection.
