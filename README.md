# AI Council V22.1 — Final Exact Names Updated Hotfix 13

Strict Free API Cascade #1 → #10 per provider. No Local Engine and no paid-model fallback.

Hotfix 13 adds an execution-identity invariant: every successful official result carries `executed_model`, and the UI may display it only when `model == executed_model`.

Run:
```bash
pip install -r requirements.txt
streamlit run app.py
```

Test:
```bash
pytest -q
```
