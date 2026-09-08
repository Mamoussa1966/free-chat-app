# AI Council V22.1 — 20-Provider Free API Cascade

This release fixes the mismatch in the previous `AI_Council_V22_1_FREE_CASCADE_10_NO_LOCAL_FINAL_HOTFIX`: the old package actually contained only five seats. This package exposes **20 provider seats** and routes each configured seat through an explicit ordered Free API cascade of up to 10 model IDs.

## Providers

1. OpenAI / ChatGPT
2. Google Gemini
3. Anthropic Claude
4. Groq
5. OpenRouter
6. Cohere
7. Mistral AI
8. xAI / Grok
9. DeepSeek
10. Together AI
11. Perplexity
12. Fireworks AI
13. Replicate
14. Hugging Face Inference Providers
15. AI21 Labs
16. Kimi / Moonshot
17. Alibaba DashScope
18. Zhipu AI / Z.ai
19. DeepInfra
20. Anyscale

## Free-only safety contract

- No Local Engine.
- No automatic paid model selection.
- No hidden model fallback.
- A provider is called only when its API credential exists **and** at least one model is explicitly configured in its `*_FREE_MODELS` secret/environment variable.
- Each provider accepts at most 10 ordered models: Free #1 → Free #10.
- Model IDs are not hard-coded as supposedly-free defaults because provider entitlements change by account, region, date, and plan.
- A successful authenticated response is the only condition used to label a council response `Official API`.

This policy is intentional: a Python application cannot manufacture a provider's free quota or entitlement.

## Current API compatibility notes

- OpenAI uses the Responses API.
- Gemini uses `generateContent` for council text/image requests.
- Anthropic uses Messages API.
- Cohere uses the current v2 Chat endpoint.
- Hugging Face uses its current OpenAI-compatible Inference Providers router.
- Replicate uses its Predictions API and accepts either an official `owner/model` reference or a version ID/reference.
- The remaining compatible providers use their documented OpenAI-style Chat Completions endpoints.

## Voice

Voice transcription is separate from the council cascade and uses Gemini `gemini-3.5-transcribe`. The model is current as of this release and can be overridden with `GEMINI_TRANSCRIBE_MODEL`.

## Attachments

Uploads are bounded to protect Streamlit memory and provider request size. Text is extracted when supported. Images are passed inline only where the provider path explicitly supports them; otherwise their extracted/metadata context is supplied as untrusted reference data.

## Run

```bash
python -m pip install -r requirements.txt
streamlit run app.py
