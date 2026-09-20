# HOTFIX145 — CONVERSATION RUNTIME + PROFESSIONAL CHAT PLATFORM FOUNDATION

Built directly from HOTFIX144. This release is additive and preserves the provider, model, Free Cascade, and Transactional Bridge contracts.

## Added
- Stable Conversation ID and Session ID per chat.
- Application-owned message ledger and round ledger.
- Request records linked to conversation/session/message identity.
- Application-owned result provenance ledger for executed provider attempts.
- Bounded conversation-context metadata with digest and message accounting.
- Synthesis metadata now carries conversation/session identity and provenance count.
- Conversation Runtime audit UI.
- Regression tests for identity stability, round/request separation, provenance safety, and Bridge ownership separation.

## Explicitly unchanged
- Official API providers only.
- No Local Engine.
- No Paid fallback.
- No automatic model selection.
- Explicit `*_FREE_MODELS` lists.
- Streamlit Secrets precedence.
- Free #1 → Free #10 cascade semantics.
- Transactional Bridge protocol and Bridge security policy.
- Provider credentials and configured model names.

## Safety rule
Provider-generated prose remains presentation data only. Conversation Runtime identity, accounting, and provenance are application-owned.
