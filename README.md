# AI Council — Free Cascade

V22.1-FINAL-EXACT-NAMES-UPDATED-HOTFIX83-FINAL

Free API Cascade #1→#10. No Local Engine, no paid fallback, and no implicit model selection.

HOTFIX83 adds a real round-scoped Shared Context Bridge. Each successful provider response is appended as untrusted reference data before the next provider call. Trusted seat/provider/executed-model identity remains authoritative and cannot be overridden by bridge content.

DeepSeek is first in bridge execution order to allow a direct DeepSeek 7 → Gemini 2 bridge test within one round. The displayed result order remains the canonical room-seat order.
