# AI Council V22.1 — HOTFIX13

Strict Free API Cascade #1→#10. No Local Engine and no paid fallback.

HOTFIX13 invariants:
- Router execution model is the authoritative `executed_model`.
- Round, History and diagnostics use the same execution identity.
- Results are unique by `(request_id, round, seat)`.
- Cascade attempts preserve candidate order and cannot skip #2.

Run `python build_release.py --check-only` then `streamlit run app.py`.
