# HOTFIX163 — Secret Boundary Final Closure

This release is built from the verified canonical V26.3/V23 runtime closure baseline.

## Closure fix
`providers.py` keeps `_streamlit_secret` as the single live/test seam for `_read_setting`:
- Secret absent -> `(None, "missing")` when no environment fallback is available.
- Secret present and empty -> `("", "streamlit_secrets_empty")` and ENV is blocked.
- Secret with `GEMINI_FREE_MODELS` -> only that explicit list is parsed.
- No Secret + no explicit model list -> `get_model_candidates(gemini) == ()` and dispatch is rejected.

The canonical V26.3 Conversation Store, Message -> Request -> Round identity chain, bridge boundary, and existing regression suite are preserved.

## Latency finding
The observed ~20-second send time is not caused by the Secret boundary. It is provider execution latency: the runtime may perform multiple official Gemini Free-cascade attempts sequentially. In the supplied runtime evidence, attempts took approximately 3.2s, 11.6s, and 21.2s before success.

This release deliberately does **not** impose a fake 1-second provider timeout, race Free models, select a model automatically, bypass the explicit Free cascade, or weaken the Request/attempt accounting. Those changes would violate the current platform contract and can make a 1-second target less reliable rather than faster.

A true sub-second **UI acknowledgement** requires a separate asynchronous/background execution architecture; it cannot honestly be guaranteed by changing the HTTP timeout alone.
