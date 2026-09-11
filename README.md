# AI Council V22.1 — FINAL EXACT NAMES UPDATED HOTFIX 14

Five official provider seats plus the user room: OpenAI/ChatGPT, Gemini, Anthropic/Claude, xAI/Grok, and Moonshot/Kimi.

## Release contract

- Free API Cascade #1 → #10 per provider.
- Only explicitly configured `*_FREE_MODELS` are eligible.
- No Local Engine and no paid fallback.
- A credential is never treated as proof that a model is free.
- Official success is recorded only when an official request returns usable text.
- Streamlit Secrets are authoritative for provider/model configuration; environment variables are used only when the corresponding Secret is absent.
- Common Unicode comma/semicolon variants are normalized before model parsing, while unsafe model identifiers are rejected.
- A non-secret model-configuration fingerprint is displayed to diagnose stale deployments without exposing credentials.
- Provider requests are bounded by an application-wide execution deadline.
- Secrets are captured before worker threads and are not read from Streamlit inside workers.
- Duplicate requests are fingerprinted from normalized prompt + attachment hashes.
- DOCX archive traversal, symlink, member-count, expansion-size, and compression-ratio checks are enforced.

## Validation

`build_release.py --check-only` performs source parsing, compilation, tests, required-file checks, and ZIP safety validation.

Python's `ast.parse()` is useful for syntax/AST validation, but Python documents that parsing alone does not guarantee compilability; the release gate therefore also compiles the sources. citeturn0search0turn0search2

ZIP members are validated before release; Python's ZIP documentation warns about unsafe archive paths and untrusted extraction. citeturn0search6

## Trust boundary

This is application-level hardening, not an operating-system sandbox. A principal that controls the deployment host, repository, environment, or Streamlit secrets can modify the application. True independent tamper resistance requires a separate trust boundary.
