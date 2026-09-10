# V22.1-FINAL-EXACT-NAMES-UPDATED-HARDENED-HOTFIX7

## Critical fix: GEMINI_FREE_MODELS authority

- `GEMINI_FREE_MODELS` is now the only source of Gemini council model candidates.
- No implicit Gemini default model is used when the Secret is missing or invalid.
- Streamlit Secrets takes precedence over environment variables when the same setting exists.
- The model list is captured once on the Streamlit script thread and passed to worker threads as an immutable tuple.
- Invalid Unicode punctuation such as `‚` no longer gets mistaken for a comma-separated model list; the UI reports the configuration as invalid instead of silently selecting another model.
- Added safe configuration diagnostics that expose only source/count/validity and never raw Secret values.
- Added regression tests for Secret precedence, no implicit default, and Unicode-comma rejection.

## Contract preserved

- Maximum 10 Free API model candidates per provider.
- Official API only.
- No Local Engine.
- No Paid fallback.
- No automatic model selection.
- A model is called only when explicitly present in the corresponding `*_FREE_MODELS` Secret/environment variable.
