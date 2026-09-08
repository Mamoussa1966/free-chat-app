V22 — Free API Cascade 1–10 / No Local
Major changes
Removed Local Engine from the council execution path.
Removed paid-model defaults from OpenAI, Anthropic, xAI, and Kimi seats.
Increased the model-cascade ceiling from 4 to 10 candidates per seat.
Added explicit *_FREE_MODELS configuration for ordered Free #1 → Free #10 routing.
The router now continues through the configured Free chain for quota, rate-limit, model, temporary, network, and provider failures.
Authentication/configuration failures stop immediately.
Official API identity remains strict: only a successful authenticated provider response is labeled Official API.
UI now reports attempted Free model sequence and never labels a local response as a provider response.
Independent diagnostics remain official-API-only.
Existing voice, attachment limits, shared context, replay protection, and parallel execution are preserved.
Important operational boundary
A Python configuration cannot manufacture Free API quota. Each configured model must genuinely be free for the API account being used. Provider pricing/entitlement changes over time, so the project deliberately avoids hard-coded claims for providers where a general Free API catalog is not established.
Validation
The release package is syntax-compiled and unit-tested locally before packaging. Live provider success still depends on the configured credential, account entitlement, quota, model availability, and network.
V22.1-FREE-CASCADE-10-NO-LOCAL
Fixed OpenAI diagnostics: authentication is now probed independently through GET /v1/models.
Explicit OpenAI diagnostic classes for 401/403/404/429/5xx and billing/quota failures.
If OpenAI authentication succeeds but OPENAI_FREE_MODELS is empty, diagnostics report AUTHENTICATED_NO_FREE_MODEL instead of falsely reporting an authentication failure.
No paid OpenAI model is selected automatically.
UI now exposes the diagnostic error and distinguishes authenticated-without-Free-model from failed API access.
V22.1 hotfix — strict Free cascade and diagnostics
Removed implicit council model defaults: every council model must come from its provider's *_FREE_MODELS Secret/environment variable.
Preserved the hard cap of 10 models per seat and ordered Free #1 → Free #10 execution.
Improved HTTP classification for 401/403/404/429 while retaining billing/quota detection.
Free cascade now continues to the next configured candidate for model, quota, permission, server, network, and request failures; credential/configuration failures remain terminal.
No Local Engine, paid fallback, or automatic model insertion was introduced.
