# 🏛️ AI Council V21

AI Council is a Streamlit-based multi-provider AI discussion room.

The architecture contains five official AI seats:

1. ChatGPT — OpenAI
2. Gemini — Google
3. Claude — Anthropic
4. Grok — xAI
5. Kimi — Moonshot

The user is the sixth participant in the room.

## Architecture

The application uses:

- `app.py` — Streamlit entry point
- `main.py` — application and room orchestration
- `providers.py` — official provider gateway
- `requirements.txt` — Python dependencies

## Provider isolation

Each provider is called independently.

A provider failure does not terminate the entire council.

Every response reports its source:

- Official API
- Local fallback
- Unavailable

The application never intentionally displays API credentials.

## Official credentials

Credentials must be supplied through Streamlit Secrets or environment variables.

Supported credentials:

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
