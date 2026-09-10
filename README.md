# AI Council V22.1 — Final Exact Names Updated / Hardened Hotfix 6

Five official provider-family seats plus the user room:
ChatGPT/OpenAI, Gemini/Google, Claude/Anthropic, Grok/xAI, and Kimi/Moonshot.

## Release contract

- Strict **Free API Cascade #1 → #10** per provider.
- Only models explicitly configured in `*_FREE_MODELS` are eligible.
- No Local Engine.
- No paid-model default.
- No automatic model discovery that silently selects a billable model.
- A credential is never treated as proof of Free Tier entitlement.
- Official status is granted only after an official provider request returns usable text.
- Authentication/configuration failures stop the cascade; candidate-specific temporary, quota/rate-limit, model, and server failures can advance to the next explicitly configured candidate.

## Security hardening

- Secrets are captured on the Streamlit main thread before worker execution.
- Worker threads receive plain snapshots and never access `st.secrets`.
- Error messages are sanitized and explicit credential values are redacted.
- User prompt and shared-context lengths are bounded.
- Provider attachment payloads have a separate safety cap.
- Upload count and total size are bounded.
- DOCX archives are checked for traversal, absolute paths, symbolic links, member count, and expansion size before text extraction.
- Per-chat request fingerprints reduce exact duplicate submissions.
- A monotonic 180-second council execution deadline bounds the whole request; provider HTTP timeouts are clipped to the remaining deadline.
- Provider response bodies are capped before JSON parsing/retention.
- Provider endpoints are HTTPS-only and model path traversal segments are rejected.
- Diagnostics and voice transcription have independent monotonic deadlines.
- Release packaging excludes prior ZIP/hash artifacts and rejects duplicate ZIP paths.
- Voice replay fingerprints are scoped per chat.
- No local result is represented as a provider response.

## Important provider boundary

This project cannot determine whether an API model is free for a particular account. Free-tier eligibility, quota, billing, model availability, and provider policy are external facts. The operator must put only genuinely zero-cost model IDs into the corresponding `*_FREE_MODELS` secret.

## Voice

Voice transcription is a separate Gemini utility path. It does not use a local engine and it does not inject a default transcription model. Configure `GEMINI_TRANSCRIBE_MODEL` explicitly.

## Run

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

## Validate

```bash
python build_release.py --check-only
```

or:

```bash
python -m py_compile app.py main.py providers.py attachment_utils.py tests/*.py
python -m unittest discover -s tests -p 'test_*.py' -v
```

## Trust boundary

The application hardens execution inside the Python/Streamlit process. It does not claim that a user who controls the deployment host, repository, environment variables, or Streamlit secrets can be made cryptographically unable to modify the application. True independent tamper resistance requires an external trust boundary.
