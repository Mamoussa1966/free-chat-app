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

## Post-merge live acceptance (separate from this test)

Before declaring the production voice path accepted:

1. Sign in to the deployed app and verify the authenticated council workspace appears.
2. In a temporary conversation, send a harmless text test and verify at least one configured
   official free provider returns a real response; do not count a spinner or diagnostics-only
   entry as a successful response.
3. Reload/open a new Streamlit connection and verify the conversation and its response persist.
4. Record a short non-sensitive audio sample, verify the preview, then test discard/reset.
5. In a separate live voice test, send a short recording and confirm a transcript plus a council
   result; the isolated browser test does not make this claim.
6. Delete the temporary test conversation and verify its voice preview/audio state is cleared
   while recordings associated with retained conversations remain intact.

Use only non-sensitive test text/audio. Keep this checklist separate from CI results: a pass in
the local harness does not prove the production app, Supabase persistence, provider availability,
or live transcription are working.

Run locally after installing `requirements.txt`, Playwright, and its Chromium browser:

```bash
python -m pip install -r requirements.txt "playwright==1.64.1"
python -m playwright install chromium
pytest -q tests/browser/test_virtual_microphone.py
```
