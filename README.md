AI Council V18 — Production Hybrid
Architecture
The room runs without any API key.
Five core seats represent the official provider families: ChatGPT/OpenAI, Gemini/Google, Claude/Anthropic, Grok/xAI, and Kimi/Moonshot.
Without a credential, a seat uses the dependency-free Local Engine and makes zero provider network calls.
With a credential, the seat attempts the official provider API only.
Any provider/model/network/quota failure falls back to the Local Engine without stopping the round.
Local output never claims to be the commercial model.
Credentials are read only from Streamlit Secrets or environment variables; there are no API-key fields in the UI.
Run
python -m pip install -r requirements.txt
streamlit run main.py
Test
python -m py_compile main.py providers.py local_engine.py
python -m unittest discover -s tests -p 'test_*.py'
Optional credentials
OPENAI_API_KEY
GEMINI_API_KEY or GOOGLE_API_KEY
ANTHROPIC_API_KEY
XAI_API_KEY
MOONSHOT_API_KEY or KIMI_API_KEY
Optional model overrides use *_MODELS or *_MODEL environment variables.
Identity policy
A result is labeled official only after a successful authenticated request to the corresponding official provider API. Local fallback is explicitly labeled local.
