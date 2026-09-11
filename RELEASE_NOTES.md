# V22.1-FINAL-EXACT-NAMES-UPDATED-HARDENED-HOTFIX12

- Preserves the complete HOTFIX9 project and test suite.
- Fixes the remaining Secrets precedence edge case: an explicitly present Streamlit Secret, including an empty value, is authoritative and cannot be replaced by an Environment Variable for the same key.
- Keeps the strict Free-only contract: no implicit provider model defaults, no Local Engine, and no paid fallback.
- Keeps Unicode mobile separators, deduplication, and the hard limit of 10 configured models per provider.
- Adds regression coverage for explicit-empty Secret precedence and live model-list changes.
- Release is built only after syntax validation, full unittest/pytest execution, ZIP integrity validation, and manifest/hash generation.

## Hotfix 13
- Preserved the complete Hotfix 12 test suite.
- Added authoritative `executed_model` identity.
- Added fail-closed UI identity checks.
- Added regression tests preventing cascade skips such as #1 → #3.
