# Virtual microphone browser smoke test

The dedicated GitHub Actions workflow runs a local, isolated Streamlit harness with
Playwright Chromium. Chromium receives a synthetic microphone via
`--use-fake-device-for-media-stream`; `--use-fake-ui-for-media-stream` and a
context-level `microphone` permission grant remove interactive permission prompts.

The test has three goals:

1. Prove the browser permission and virtual device can produce a non-empty recording.
2. Exercise the real Streamlit `st.audio_input` widget, prove bytes reach Python, and
   verify the preview can be discarded before the local send button is clicked.
3. Guard the production `main.py` voice-control label/order and the discard nonce reset.

The test harness is not the production app. It has no Supabase session, API keys,
persistent storage, or provider calls, and it never visits the deployed app or sends
audio to the council. Therefore, a pass verifies the browser/audio-input test foundation
and a source-level contract; it does not claim to prove live authentication, Gemini
transcription, or successful delivery to the council.

Run locally after installing `requirements.txt`, Playwright, and its Chromium browser:

```bash
python -m pip install -r requirements.txt "playwright==1.64.1"
python -m playwright install chromium
pytest -q tests/browser/test_virtual_microphone.py
```
