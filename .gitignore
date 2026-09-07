# 🏛️ AI Council V21.11

AI Council is a Streamlit-based multi-provider AI discussion room.

The application provides one shared council room containing:

1. ChatGPT — OpenAI
2. Gemini — Google
3. Claude — Anthropic
4. Grok — xAI
5. Kimi — Moonshot

The user is the sixth participant.

---

## Architecture

The application is intentionally split into isolated layers:

- `app.py`
  - Streamlit entry point.
  - Imports and calls `run_app()` from `main.py`.

- `main.py`
  - Application orchestration.
  - Six-room UI.
  - User message handling.
  - Shared council context.
  - Attachments.
  - History management.
  - Diagnostics.
  - Parallel provider execution.

- `providers.py`
  - Official provider gateway.
  - Provider-specific request/response handling.
  - Credential isolation.
  - Model candidate selection.
  - Error classification.
  - Secret redaction.
  - Provider failure isolation.

- `attachment_utils.py`
  - Attachment validation.
  - Filename sanitization.
  - Size and count limits.
  - Duplicate detection.
  - Safe text extraction.

- `local_engine.py`
  - Explicitly declared local fallback engine.
  - It must never impersonate an official provider.

- `requirements.txt`
  - Runtime Python dependencies.

- `tests/`
  - Unit and structural tests.
  - Tests must pass before considering a release candidate.

---

## Council execution model

A user message is submitted once.

The application then attempts to deliver the same logical request to the five official provider seats independently.

Provider execution is isolated.

Therefore:

- One provider failure must not terminate the other providers.
- A timeout from one provider must not block the entire council indefinitely.
- Authentication failures must be reported separately.
- Rate-limit/quota failures must be reported separately.
- Invalid or unavailable models must be reported separately.
- Network/provider failures must be reported separately.
- A provider must never be marked successful merely because its API key exists.

The application distinguishes between:

- `Official API`
- `Local fallback`
- `Unavailable`
- `Failed`

Credential presence is configuration state only.

It is NOT proof that an API call succeeded.

---

## Credential handling

API credentials must be supplied through Streamlit Secrets or environment variables.

Supported credential aliases include:

```text
OPENAI_API_KEY

GEMINI_API_KEY
GOOGLE_API_KEY

ANTHROPIC_API_KEY
ANTHROPIC_WORKSPACE_ID
CLAUDE_WORKSPACE_ID

XAI_API_KEY
GROK_API_KEY

KIMI_API_KEY
MOONSHOT_API_KEY
