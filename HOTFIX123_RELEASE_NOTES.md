# HOTFIX123 — BRIDGE/SECURITY + DEPLOYED RELEASE IDENTITY GATE

## Scope
- Freeze and expose the deployed runtime identity before Bridge/Security changes.
- Preserve the existing canonical conversation store and verified history hash path.
- Harden the Transactional Bridge diagnostic so its canary is application-owned, round-scoped, and never copied into the user prompt or Gemini input.
- Preserve one Request → one Round → one Bridge identity; Free Cascade attempts remain inside the same Request.

## Bridge/Security contract
A successful runtime proof must show:
- WRITE = PASS
- VALIDATE = PASS
- COMMIT = PASS
- BARRIER = PASS
- READ = PASS
- SCHEMA_VALIDATION = PASS
- MATCH = PASS
- USER_PROMPT_CONTAINS_VALUE = NO
- GEMINI_INPUT_PROMPT_CONTAINS_VALUE = NO
- BRIDGE_STATE_CONTAINS_VALUE = YES

The diagnostic canary is explicitly marked `write_origin=APPLICATION_TEST_CONTROL`; it is not inferred from model prose. The logical source remains DeepSeek / Seat 7 and the target remains Gemini / Seat 2.

## Release identity
The release identity gate records the observed Provider Core / Hotfix / Platform layers and the VERSION.txt layer without silently rewriting any of them. This is intentional: a deployment mismatch must be visible rather than normalized away.

## Preservation
- No provider credentials changed.
- No model lists changed.
- No Free Cascade policy changed.
- No Local Engine or Paid fallback added.
- Canonical conversation persistence and canonical history hash verification remain in place.
- No baseline files deleted.
