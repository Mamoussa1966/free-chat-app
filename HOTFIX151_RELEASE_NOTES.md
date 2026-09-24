# HOTFIX151 — V23 FULL AUDIT COPY / DOWNLOAD UX

## Scope
HOTFIX151 is a narrow UI/export layer above HOTFIX150. It makes the long V23 Platform Audit easy to capture from a mobile device.

### Added
- Native Streamlit copyable code block containing one complete V23 audit export.
- Download button producing `V23_FULL_PLATFORM_AUDIT.json`.
- Export includes the platform audit, final closure audit, security audit, provider health snapshot, and Production Core report/code.
- Export is generated only after the existing `Run full V23 platform audit` action has produced its runtime artifacts.

### Explicitly unchanged
- Secrets / credentials
- Models / model lists
- Free Cascade
- Provider adapters
- Seat count
- Request/round/message counters
- Canonical persistence and identity binding
- Bridge semantics
- Synthesis semantics
- Existing audit execution logic

No audit result is converted from NOT_RUN/NOT_PROVEN to PASS by this layer.
