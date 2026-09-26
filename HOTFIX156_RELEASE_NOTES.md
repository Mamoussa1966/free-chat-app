# HOTFIX156 — MOBILE UX UNIVERSAL COPY / PRINT / DOWNLOAD + MULTILINE COMPOSER

## Closure correction
A post-release UI review found that the first HOTFIX156 package returned from `run_app()` when the multiline composer was idle. Because Streamlit reruns on mobile while the user edits the text area, that early return prevented all sections below the composer from rendering.

This corrected HOTFIX156 removes only that idle-path return. Request execution remains exclusively gated by the explicit **📨 إرسال إلى المجلس** button (or the existing voice-submission path). The complete audit/provider/runtime sections continue to render during idle composer reruns.

## Mobile UX
- Enter inserts a newline in the multiline composer.
- Explicit Send button owns request submission.
- Copy / Print / Download controls remain presentation-only.
- No provider, cascade, request identity, persistence, security, or audit authority changes.

## Verification
- HOTFIX156 mobile UI tests: 6 passed.
- Full regression suite: 538 passed.
- Package preserves the 438-file HOTFIX156 working baseline.
