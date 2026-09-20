# HOTFIX137 — Initial Request / Continuation Intent Hardening

Base: HOTFIX135 production regression release.

## Root cause fixed
The continuation gate treated the mere word `continuation` as a continuation command.
A new-chat regression/diagnostic prompt that said `do not use Continuation` could therefore
enter the fail-closed continuation path before the first Request ID was allocated.

## Fix
- Continuation classification now requires explicit continuation intent.
- An explicit Request ID remains sufficient to identify a continuation target.
- Negated mentions such as `do not use Continuation` no longer trigger the gate.
- Unknown/invalid explicit continuation IDs remain fail-closed and never allocate a new ID.
- Normal first Requests continue through the ordinary Request Lifecycle and receive a new
  application-owned Request ID.

No Secrets, model lists, cascade order, provider contracts, Local Engine, Paid fallback,
or automatic model selection were changed.
