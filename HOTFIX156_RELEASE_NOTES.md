# HOTFIX156 — Mobile Chat UX + Universal Section Actions

## Scope
- Mobile-first multiline message composer using `st.text_area`.
- `Enter` inserts a newline; explicit **📨 إرسال إلى المجلس** submits the message.
- Direct mobile file/image upload remains available before submission.
- Added reusable section action controls: **📋 نسخ**, **🖨️ طباعة**, **⬇️ Download**.
- Applied to HOTFIX118, Conversation Runtime, provider diagnostics, round diagnostics, Transactional Bridge, Authoritative Request Audit, HOTFIX131 isolation, Production Core, Council Synthesis, HOTFIX141, V23 Final Closure, and A/B/C lifecycle audit.
- Added Print to the existing V23 platform audit action bar.

## Integrity
- UI/presentation-only changes; no provider, model, Free Cascade, Request/Round identity, persistence, security, or audit authority changes.
- Baseline HOTFIX155 package preserved; only HOTFIX156 UI/test/release-note files were added or modified.

## Verification
- HOTFIX156 focused UI tests: 5 passed.
- Full regression suite: expected to pass after updating HOTFIX151 action-bar assertions to the intentional four-button V23 bar.
