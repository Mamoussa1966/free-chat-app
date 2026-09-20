# HOTFIX137 — RESTORED HOTFIX134 BASELINE

- Base is the verified HOTFIX134 archive from the project library.
- HOTFIX135 multi-request regression layer is intentionally removed because the user reported that HOTFIX135 introduced the current failure behavior.
- No changes to provider credentials, explicit Free model lists, cascade policy, Local Engine, Paid fallback, or automatic model selection.
- No continuation semantics were added or broadened. Existing HOTFIX125/126 fail-closed continuation rules from the HOTFIX134 baseline remain intact.
- Only release identity is updated to HOTFIX137.
