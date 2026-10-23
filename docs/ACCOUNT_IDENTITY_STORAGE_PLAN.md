# AI Council: Account Identity and Durable Conversation Storage

**Status:** Phase 1 design contract (proposal; not production implementation)  
**Baseline branch:** `gitops-v0.4-final`  
**Baseline commit reviewed:** `8c1b447d88efd40f4e2e680cc29e72e3c3c5a57d`  
**Product constraint:** free-tier services only; no paid API fallback and no local model engine.

## 1. Why this work is needed

The inspected runtime path initializes the canonical persistence store through `ensure_persistence_store(st.session_state)`. `conversation_persistence_v26.py` keeps a compatibility alias to the same canonical store, while `export_engine.py` exports the authoritative conversation snapshot. The inspected `requirements.txt` declares Streamlit, Requests, and pytest, but does not declare a database client. These facts do not establish durable, cross-restart storage in the deployed app.

The next product capability should let a user securely identify their own account and, once an explicitly selected storage service is configured, retrieve their conversations across browser sessions and app restarts. This must not weaken the current canonical Message → Request → Round identity rules.

## 2. Scope of this phase

This document defines the decisions and acceptance gates only. It does **not** add login, a database, new secrets, or production UI behavior. Keeping this first PR documentation-only lets CI verify the existing baseline before implementation is split into small, reviewable changes.

## 3. Non-negotiable invariants

1. Keep `gitops-v0.4-final` protected. All changes enter through a Pull Request and the required `CI / regression-and-package` check.
2. Do not alter `VERSION.txt`, frozen provider identity, HOTFIX164.30 release identity, or release manifests as part of account/storage work.
3. Preserve one canonical conversation store and the existing Message → Request → Round bindings. Reads, authentication checks, hydration, and audits must not create new Requests, Messages, or Rounds.
4. Keep provider credentials, access tokens, raw credential payloads, and secret values out of conversation records, exports, user-visible errors, CI logs, and telemetry.
5. Authorize every conversation read, write, export, and delete on the server. Never rely on a hidden UI control or a client-provided conversation ID as authorization.
6. Use the stable identity supplied by a verified identity provider (issuer + subject) as the account key. Do not use an email address or display name as the immutable account ID.
7. Preserve the existing guest/session flow until migration behavior is explicitly designed and tested. Never silently attach an anonymous conversation to a signed-in account.
8. Free-only remains a hard constraint. Do not introduce a paid service, paid API fallback, or local inference engine. Evaluate current quotas, retention, backups, data region, and free-tier limits before selecting a storage vendor.

## 4. Proposed architecture boundaries

- **Identity adapter:** validates the identity-provider result and returns a minimal internal identity (`issuer`, `subject`). The concrete provider and configuration method remain undecided until verified against current service terms and supported Streamlit behavior.
- **Conversation repository interface:** provides explicit operations for saving and loading canonical conversation snapshots. Runtime code should not embed vendor-specific SQL or API calls throughout `main.py`.
- **Ownership enforcement:** each durable conversation must be associated with one verified account identity. Every repository operation checks ownership in the server-side query or policy layer.
- **Canonical records:** persist the canonical Message, Request, and Round identity records without using provider-generated prose as authoritative identity. Preserve idempotency and conflict detection.
- **Guest migration:** keep guest data separate by default. Any “save this guest conversation to my account” flow must be explicit, ownership-checked, transactional, and covered by tests.
- **Export and deletion:** provide an account-scoped export/delete path only after ownership checks. Deletion semantics and any required retention window must be decided before enabling deletion in production.

## 5. Implementation sequence and gates

### Phase A — this PR: design contract

- Add this document only.
- Do not modify application code, dependencies, Secrets, workflows, release identity, or branch rules.
- Require normal CI to pass before considering the document accepted.

### Phase B — repository interface and tests

- Add a small repository interface behind the existing canonical-store boundary.
- Add unit tests using a deterministic fake/in-memory adapter; do not require real credentials or network access in CI.
- Prove ownership isolation, idempotent writes, conflict rejection, and no identity allocation during read/hydration/audit.

### Phase C — storage adapter

- Select a service only after checking its current free-tier limits, persistence guarantees, backup/recovery options, privacy terms, and data location.
- Add schema/migrations and adapter tests without enabling the feature in the deployed UI.
- Fail closed on ownership uncertainty or storage errors; do not silently report a save as successful when it failed.

### Phase D — authentication integration

- Implement identity through a verified identity-provider flow, with explicit missing/invalid-identity handling and logout behavior.
- Keep the feature disabled until required deployment configuration is present and validated.
- Never put credentials or tokens in source control or seed them in test fixtures.

### Phase E — gated rollout

- Test two different accounts and prove neither can read, export, modify, or delete the other's conversations.
- Test persistence across a fresh app process/session, guest-mode compatibility, provider outage, and account logout/login.
- Perform a live smoke test on a non-production/staging deployment before any production enablement.

## 6. Required acceptance tests before enabling the feature

- Verified account A can load only account A's conversations; account B cannot retrieve them even when given an account A conversation ID.
- Missing, malformed, or unverified identity is denied access to account-owned records.
- Guest conversations remain usable and are not implicitly reassigned on login.
- Canonical Message → Request → Round identities remain stable through save, reload, retry, and rerun.
- Repeated writes are idempotent; identity conflicts fail visibly and safely.
- Read-only operations and audits do not allocate IDs or create lifecycle records.
- Storage outage does not produce a false “saved” success state; the user receives a safe, actionable message.
- Exports contain no API keys, access tokens, or internal secrets.
- Tests run without live provider credentials, paid APIs, or an external database.
- Required GitHub Actions check `CI / regression-and-package` passes on the PR head.

## 7. Out of scope for this document PR

- Enabling login in the production app.
- Selecting or provisioning a database/vendor.
- Adding or changing Streamlit Secrets.
- Changing dependencies, `main.py`, `app.py`, `providers.py`, `VERSION.txt`, release manifests, branch protection, or CI workflows.
- Claiming durable persistence or production authentication before the relevant implementation and live verification exist.

## 8. Review checklist

- [ ] The PR contains only this design document.
- [ ] The base branch is `gitops-v0.4-final`.
- [ ] The `CI / regression-and-package` required check passes.
- [ ] No Secrets, provider keys, release identity files, or production code changed.
- [ ] The PR remains unmerged until reviewed and the next implementation slice is agreed.
