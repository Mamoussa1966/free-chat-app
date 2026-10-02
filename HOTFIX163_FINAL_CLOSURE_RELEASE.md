# HOTFIX163 — Final Regression Closure Release

## Purpose

This artifact is a substantive final-closure build, not a filename-only rename of HOTFIX163.2 or HOTFIX163.3.

## Production fix retained

`providers.py` uses `_streamlit_secret` as the single Streamlit Secret resolution seam for `_read_setting`.
A missing Secret is represented as `None`; an explicitly empty Secret is represented as `""` and remains authoritative over an environment value.

The resolver no longer performs a second direct `_streamlit_secret_state` lookup from `_read_setting`, which prevents a no-secret isolation test from being bypassed by a live `st.secrets` value.

## Final regression lock

`tests/test_hotfix163_final_closure.py` adds two focused tests:

- the no-secret seam cannot be bypassed by live Secret state;
- an explicitly empty Secret blocks a stale environment model list at the canonical read boundary.

No existing test was weakened, skipped, edited to manufacture PASS, or suppressed.

## Release contract

`VERSION.txt` remains:

`V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`

This is intentional: the canonical runtime/provider version contract is preserved while HOTFIX163 is treated as the regression-closure release layer.

## Acceptance

The release is closed only when:

1. the complete pytest suite passes with `FAILED=0`;
2. the exact ZIP extracts with `main.py`, `conversation_store.py`, and `tests/` directly at its root;
3. the complete suite passes again from the extracted ZIP;
4. no nested ZIP, runtime Secret, or symlink is packaged.
