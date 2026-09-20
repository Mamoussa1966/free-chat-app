# HOTFIX140 — A/B/C INDEPENDENT REQUEST LIFECYCLE HARDENING

Built directly from HOTFIX139; no Secrets, Models, Free Cascade, Local Engine, Paid fallback, or Bridge policy changes.

## Fixes
- Published/runtime release identity is now explicitly `V23.0-HOTFIX140-A-B-C-LIFECYCLE-HARDENED`; the stale HOTFIX137 provider identity is removed from the active version string.
- Added an application-owned A/B/C Multi-Request Lifecycle Audit. It is observational and cannot fabricate Requests or provider executions.
- The audit requires three persisted Request Records with three unique Request IDs, unique Bridge IDs where Bridges exist, and zero duplicate Seat+Round executions.
- Fresh-request semantics remain the default. Continuation is still explicit first-line control only.

## Required runtime proof
Send A, B, and C as three separate chat submissions. Do not put A/B/C into one ordinary user message; one normal chat submission creates one Request lifecycle.

## Validation
Full regression suite and packaged-artifact validation are required before release.
