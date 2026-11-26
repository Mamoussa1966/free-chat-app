# Clerk Hobby isolated authentication pilot

**Status:** Isolated test pilot / Draft. No production rollout is authorized.
**Production baseline:** `gitops-v0.4-final` at `b4883ff5f33aa721c42909a2b09a2f2baf8325e8`.
**Test Supabase project:** `ai-council-storage-test` (`pidcepvwsezdrlhxqksg`, `ap-south-1`).
**Clerk instance:** Development, issuer `https://dear-hermit-1240.clerk.accounts.dev`.
**Production Supabase and Cloudflare Worker Admin:** explicitly out of scope.

## Decision

Use Clerk Hobby as the candidate end-user identity provider for this isolated pilot under the project's strict $0 requirement. Clerk's compromised-password protection is enabled in the Development instance and the current Supabase first-party Clerk Third-Party Auth integration is enabled. Do not use the deprecated shared-Supabase-JWT-secret/JWT-template integration.

This is the best operational fit under the currently verified constraints (hosted service, strict $0, direct Supabase integration, HIBP). It is not a universal claim that Clerk is the strongest identity platform. A self-hosted authentik deployment offers HIBP plus MFA, but would require continuously available hosted infrastructure. Clerk Hobby does not include production MFA, so it must not replace or weaken the existing Supabase Auth AAL2 path for Cloudflare Worker Admin.

## Existing schema constraints

The existing `public.council_conversations` table is not directly compatible with Clerk subjects:

- `owner_id` is a UUID foreign key to `auth.users(id)`.
- Existing owner RLS policies use `auth.uid()`, which casts JWT `sub` to UUID.
- Clerk subjects are opaque text identifiers.

Do not cast, truncate, hash, or synthesize UUIDs from Clerk subjects. Do not alter the existing conversation table, its foreign key, triggers, RLS policies, or the Cloudflare admin operator table as part of this pilot.

## Isolated test-project schema provisioning (not production migrations)

The Clerk pilot table exists only in the dedicated test project. Its provisioning scripts are deliberately kept under `tests/fixtures/supabase/`, not in the standard `supabase/migrations/` directory that feeds the production migration chain.

The hosted test project was provisioned with these two scripts on the isolated project only:

1. `tests/fixtures/supabase/20261110123054_clerk_auth_pilot_isolated_rls.sql`
   Creates only `public.clerk_auth_pilot_records`, enables RLS, pins the restrictive issuer policy to exactly `https://dear-hermit-1240.clerk.accounts.dev`, and adds per-operation owner policies comparing `owner_subject` with JWT `sub`.
2. `tests/fixtures/supabase/20261110125010_clerk_auth_pilot_restrict_table_grants.sql`
   Revokes inherited/default `PUBLIC` and `anon` table privileges, then grants CRUD only to `authenticated`.

The local pgTAP test now creates or normalizes the same schema and policies inside its own transaction and rolls them back at the end. It does not depend on the fixture scripts being discovered as standard migrations.

Read-only verification on the hosted test project previously confirmed:
- RLS is enabled.
- `anon` has no SELECT privilege.
- `authenticated` has the intended SELECT/INSERT/UPDATE/DELETE privileges.
- The exact restrictive issuer policy and four owner policies exist.
- The production conversation table, Cloudflare operator table, and production resources were not changed.

The test project's migration history still records its earlier isolated setup. Do not run production `db push`, merge this pilot, or copy these fixtures into `supabase/migrations/` as part of this task.

## Database RLS test coverage

Added `supabase/tests/clerk_auth_pilot_rls.test.sql` to the local Supabase pgTAP workflow. It verifies:
- RLS is enabled and `anon` lacks SELECT privilege.
- Clerk issuer + subject A can insert/read its own record.
- Clerk user B cannot read, modify, delete, or spoof ownership of A's record, but can insert/read its own record.
- A token with the native Supabase Auth issuer cannot read or insert into the Clerk pilot table.
- A token with a wrong issuer cannot read or insert.
- User A's original data remains unchanged after B's attempted modification/deletion.

The first local RLS run exposed three test expectation issues (3 failures out of 17); these were corrected. The current workflow on branch head `335f93c4f6754a01f1aaa1f9f7bb7b392a9ca833` completed successfully: **54 pgTAP tests passed across all 3 SQL test files**, including the Clerk pilot suite.

The workflow applies the test fixtures in a disposable local Supabase stack and runs `supabase test db --local`. These tests use synthetic JWT claim contexts. They prove the SQL policy behavior under those contexts, but do not replace a live request authenticated with an actual Clerk or native Supabase Auth JWT. External-token acceptance gates remain separate.

## Streamlit Clerk UI and server-side JWT verification

Implemented on the isolated branch:

- `clerk_streamlit_auth.py` registers a Streamlit Components v2 UI using ClerkJS 6 and Clerk UI 1 from the pinned Clerk Development Frontend API. The sign-in, sign-up, account button, and sign-out are rendered in the actual Streamlit page context; no Next.js runtime or `NEXT_PUBLIC_*` naming is used.
- `pages/11_Clerk_Auth_Pilot.py` provides a separate test-only login and PostgREST validation page. It does not alter the main application's Supabase Auth gate or the Cloudflare Worker Admin page.
- The public `pk_test_` Publishable Key and the Development domain are test-only defaults in the module; the public key can also be overridden through `CLERK_TEST_PUBLISHABLE_KEY`. No Clerk `sk_test_`/Secret Key is required.
- The component follows Clerk's documented CDN bootstrap: it loads `@clerk/ui@1`, then loads `@clerk/clerk-js@6` with `data-clerk-publishable-key` and uses the resulting `window.Clerk` singleton. The UI provides sign-in/sign-up, UserButton and sign-out. It obtains a short-lived Clerk session token and forwards it to the Streamlit server through the bidirectional Components v2 state channel. It does not copy tokens into a custom localStorage store, URLs, application logs, or conversation records. The server keeps the current token only in Streamlit server-side session state and re-verifies it on every page run; the browser SDK refreshes it while the page remains open.
- The Python verifier fetches the public JWKS from `https://dear-hermit-1240.clerk.accounts.dev/.well-known/jwks.json`, caches the key set for five minutes, and verifies the RS256 signature before trusting any claims. It requires `iss`, `sub`, `sid`, `exp`, `iat`, `nbf`, `azp`, and `role`; pins `iss` to the configured Clerk Development issuer; requires `role=authenticated`; and requires `azp` to match the exact allow-listed Streamlit origin. Unknown signing keys, unsupported algorithms, wrong issuers/origins, missing claims, and expired tokens fail closed.
- The authorized party is not defaulted. A separate Streamlit test deployment must explicitly set `CLERK_TEST_AUTHORIZED_PARTIES` in that test app's server-side Secrets to its exact HTTPS origin. The live production app origin is explicitly denied by the module. The verifier fails closed if the `azp` claim is missing or is not one of those exact origins.
- The page uses the verified Clerk token as the PostgREST Bearer token and the test project's publishable key. It can create/read/delete only the isolated pilot records owned by the verified Clerk subject, and provides an explicit negative test for owner spoofing.
- The existing `SupabaseConversationRepository` remains UUID/Supabase-Auth-only. No attempt was made to coerce Clerk IDs into UUIDs or to redirect ordinary council conversation storage to the pilot table.

The Publishable Key is public configuration, not a secret. The test code deliberately contains only the test Publishable Key and test project Publishable Key. It contains no Clerk Secret Key, Supabase service-role key, Supabase JWT signing secret, or any production credential.

## JWT verification implementation

The pilot deliberately uses the repository's existing `cryptography==50.0.2` dependency plus `requests`; it does not add or change `requirements.txt`. It implements the narrow RS256/JWKS verification path directly:

- The JWKS URL is constructed from the pinned Clerk Development issuer. No `jku`, `x5u`, or other URL from the untrusted token is followed.
- The token is size-bounded and split into exactly three compact-JWT segments. The header and payload are parsed as untrusted data; no claim is acted on until the RSA signature verifies.
- Only `alg=RS256` and a non-empty bounded `kid` are accepted.
- The matching JWK must be an RSA signing key with a modulus of at least 2048 bits.
- The RSA signature is verified using PKCS#1 v1.5 with SHA-256.
- The verified claims are then checked for the exact issuer, user/session ID shape, expiry, not-before and issued-at times, the expected `azp` origin, and `role=authenticated`.
- The pinned issuer's JWK set is cached in process memory for five minutes. An unknown `kid` can trigger a refresh only once per 30-second window, so arbitrary headers cannot force one JWKS network request on every failed token.

This keeps the dependency contract unchanged and ensures the application does not rely on a generic JWT parser's pre-verification behavior for untrusted tokens.

## Authorized-party deployment boundary

The production Streamlit origin is intentionally excluded from this pilot. The currently deployed isolated test app is pinned in code to exactly:

`https://free-chat-app-vrbyn5tesfyhhz5skphzn5.streamlit.app`

The verifier does not accept the production origin or arbitrary runtime origins. This source-level allowlist is intentionally stricter than a user-editable environment value. Do not add `CLERK_TEST_AUTHORIZED_PARTIES` to the production app, and do not reuse or modify production settings. The test app must continue to be deployed from `security/clerk-hobby-test-pilot`, with the Clerk Development issuer and the isolated Supabase test project only.

## Security acceptance gates — still pending

Before any app integration can be called safe, verify with real, short-lived session tokens:
1. Clerk user A can insert, read, update, and delete only A's pilot rows.
2. Clerk user B cannot read/update/delete A's rows or insert a row claiming A as owner.
3. A native Supabase Auth JWT is denied read/insert/update/delete on the pilot table despite its `authenticated` role.
4. Wrong-issuer, missing-role, expired, unknown-`kid`, and invalid-signature tokens are denied.
5. Clerk password protection rejects a known test-only compromised password during password creation/change and follows the documented compromised-password sign-in remediation path.
6. Sign-out, token refresh, browser refresh, and account switching are tested.
7. Cloudflare Worker Admin's separate Supabase Auth AAL2 path remains unchanged and verified separately.

Where the application uses Storage, Realtime, or Edge Functions, apply and test the corresponding issuer restrictions there too. A table-level PostgREST test does not prove protection for other Supabase services.

## Streamlit integration constraints

The current `SupabaseConversationRepository` explicitly requires the Supabase Auth issuer and a UUID subject. It must not be loosened to accept Clerk tokens by decoding claims without signature verification or by coercing subjects to UUIDs.

A future test-only adapter must independently verify Clerk JWT signatures against the issuer's published JWKS and validate issuer, expiry, subject, role, and relevant audience/authorized-party claims. The browser must use Clerk's supported SDK; session tokens must remain short-lived and must not be written to logs, conversation history, URLs, or browser localStorage by custom code. Any feature flag must fail closed unless the configured Supabase URL and Clerk issuer exactly match this test allowlist.

The Clerk publishable key is public browser configuration; Streamlit does not use the Next.js-specific `NEXT_PUBLIC_` naming convention. The key must remain test-only configuration and must not be hardcoded into application source.

No AI provider requests are needed for this authentication pilot.

## Plan, billing, and key constraints

- Keep the pilot within Clerk Hobby and Supabase Free quotas; stop before any paid tier, card, overage, or billable feature is activated.
- The Clerk publishable key is public configuration; any secret key must remain server-side and must never be committed.
- Never place a Supabase service-role/secret key or project JWT signing secret in the browser, Clerk dashboard, or repository.
- Do not request or store user passwords or raw authentication tokens in chat.

## Current verified status — evidence refreshed 2026-11-26

### GitHub and CI evidence

- Production branch `gitops-v0.4-final` remains at `b4883ff5f33aa721c42909a2b09a2f2baf8325e8`.
- Test branch head is `335f93c4f6754a01f1aaa1f9f7bb7b392a9ca833` (2026-11-25 17:49:37 UTC).
- PR #112 remains **open, Draft, and unmerged**, targeting `gitops-v0.4-final`. No production merge or deployment was performed.
- AI Council CI on the current test head: **1061 passed, 2 skipped**. The full release candidate, ZIP integrity, SHA-256 sidecar, and release identity checks passed. The CI attestation explicitly reports `live_deployment_closure_proven: false`; this is not evidence that production is deployed from this candidate.
  - PR CI: https://github.com/Mamoussa1966/free-chat-app/actions/runs/45668826831
  - Push CI / release artifact: https://github.com/Mamoussa1966/free-chat-app/actions/runs/45668817862
- Supabase RLS workflow on the same head: **54 pgTAP tests passed across 3 SQL files**.
  - https://github.com/Mamoussa1966/free-chat-app/actions/runs/45668826770
- Dependabot Python Compatibility and Supabase Preview were skipped for this head; do not count them as passing live checks.

### Current hosted test-project database evidence

A read-only SQL query on `ai-council-storage-test` (`pidcepvwsezdrlhxqksg`) returned:

- `clerk_auth_pilot_records`: 2 records.
- Distinct `owner_subject` values: 1. This is not yet a real two-Clerk-account isolation proof.
- Native Supabase Auth users: 4. The count alone does not establish that any one of them is a second Clerk identity.
- RLS enabled: true.
- Policies on the pilot table: 5.
- Direct `anon` SELECT grants: 0.

Earlier real-browser evidence established one working Clerk user session, access to that user's two test records, and rejection of an owner-spoof attempt. Sign-out followed by sign-in again restored the same account's session and its own records. This does not yet prove independent two-account isolation, live token refresh/expiry, or account switching.

### Native Supabase Auth negative probe

- Added `pages/12_Supabase_Native_Auth_Denial_Probe.py` with current build marker `SUPABASE-NATIVE-AUTH-DENIAL-PROBE-SECURE-INPUT-20261125`.
- It signs into the native Supabase Auth test account from the browser, validates the issued token through `/auth/v1/user`, checks the JWT issuer/role/subject, and attempts both table read and a narrowly keyed insert-denial probe.
- Password and bearer token are not written to Streamlit state, browser storage, URLs, or output. A successful unexpected insert is immediately targeted for cleanup and is reported as a failure, not a pass.
- **This live browser probe has not yet been executed.** Only a test-only Supabase Auth password may be entered into this page; never send the password or token in chat.

### Duplicate email investigation

- Clerk's email-code handler currently contains one `prepareFirstFactor({strategy: "email_code", ...})` call and a single-flight `signInBusy` guard. Unit coverage asserts one send call and no resend path in this handler.
- One Clerk `email.delivered` event was supplied for the reported incident: `01a1cc44-a094-7ad1-a348-267d557ae17f` at 2026-11-11 23:20:12 Riyadh time, SMTP status 250.
- That single event does not explain why Gmail displayed two messages. The second Clerk email event (if present) and the two Gmail RFC `Message-ID` values have not yet been correlated. Do not claim the duplicate-delivery root cause is resolved.
- The earlier sign-in/session flow and the static single-call guard are not substitutes for event correlation.

### Remaining live acceptance gates

1. Run the native Supabase Auth denial page using a test-only native Supabase Auth account; confirm the real token is validated and the pilot table denies the read/insert operations.
2. Use a second, distinct Clerk Development account to prove owner isolation with real sessions. Do not infer a second Clerk account from the four native Supabase Auth users.
3. Complete real browser session refresh, expiry, sign-out, and account-switch acceptance; automated tests cover portions of the code path but not the full live browser behavior.
4. Correlate the duplicate Gmail messages against Clerk Email Logs and Gmail RFC `Message-ID` values.
5. Reconfirm the production runtime SHA and existing AAL2-protected Cloudflare Worker Admin path separately before any future production-auth decision.

### Cost and scope guardrails

- Clerk Hobby currently lists a free tier with 50,000 monthly retained users per app and email-code authentication; the published plan excludes MFA. Supabase Free lists 50,000 Monthly Active Third-Party Users. Usage and plan limits must be monitored; do not switch to paid plans or enable billable add-ons.
- Clerk Hobby's lack of MFA is why this pilot must not replace or weaken the existing Supabase Auth AAL2 requirement on Cloudflare Worker Admin.
- No production database, production secrets, production Auth configuration, Cloudflare Worker, AI provider, or production deployment was changed by this test branch work.

## Official references

- Clerk password protection: https://clerk.com/docs/guides/secure/password-protection-and-rules
- Clerk pricing: https://clerk.com/pricing
- Supabase Clerk integration: https://supabase.com/docs/guides/auth/third-party/clerk
- Supabase Third-Party Auth and restrictions: https://supabase.com/docs/guides/auth/third-party/overview
- Supabase custom OIDC requirements and issuer restrictions: https://supabase.com/docs/guides/auth/third-party/custom-oidc
- authentik password policy: https://docs.goauthentik.io/customize/policies/types/password/
- Cloudflare Containers pricing: https://developers.cloudflare.com/containers/platform/pricing/
