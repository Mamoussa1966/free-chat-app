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

## Applied isolated test migrations

The test project has two dedicated migrations:

1. `20261110123054_clerk_auth_pilot_isolated_rls`
   `supabase/migrations/20261110123054_clerk_auth_pilot_isolated_rls.sql`
   Creates only `public.clerk_auth_pilot_records`, an isolated table whose owner subject is text. It enables RLS, adds a **restrictive** issuer policy pinned to exactly `https://dear-hermit-1240.clerk.accounts.dev`, and per-operation owner policies comparing `owner_subject` with the JWT `sub`.
2. `20261110125010_clerk_auth_pilot_restrict_table_grants`
   `supabase/migrations/20261110125010_clerk_auth_pilot_restrict_table_grants.sql`
   Revokes inherited/default `PUBLIC` and `anon` table privileges, then grants CRUD only to `authenticated`.

Both migrations are applied and recorded in the hosted test project's migration history. Read-only verification confirms:
- RLS is enabled.
- `anon` has no SELECT privilege.
- `authenticated` has the intended SELECT/INSERT/UPDATE/DELETE privileges.
- The exact restrictive issuer policy and four owner policies exist.
- The pilot table contains zero rows.
- `public.council_conversations`, `private_cloudflare.worker_admin_operators`, Supabase Auth users, and all production resources remain unchanged.

## Database RLS test coverage

Added `supabase/tests/clerk_auth_pilot_rls.test.sql` to the local Supabase pgTAP workflow. It verifies:
- RLS is enabled and `anon` lacks SELECT privilege.
- Clerk issuer + subject A can insert/read its own record.
- Clerk user B cannot read, modify, delete, or spoof ownership of A's record, but can insert/read its own record.
- A token with the native Supabase Auth issuer cannot read or insert into the Clerk pilot table.
- A token with a wrong issuer cannot read or insert.
- User A's original data remains unchanged after B's attempted modification/deletion.

The first run exposed three test expectation issues: the table inherited a default `PUBLIC`/anon grant, and PostgreSQL's RLS error message includes the restrictive policy name. Both were corrected with the second migration and updated assertions. The **initial RLS test run failed (3 of 17)**; the corrected rerun on the latest branch is pending. Do not interpret the earlier run as a pass.

The workflow applies versioned migrations in a disposable local Supabase stack and runs `supabase test db --local`. These are synthetic local JWT-claim tests, not proof of a real browser sign-in or a live Clerk session token. The live external-token acceptance tests below remain required.

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

The production Streamlit origin is intentionally excluded from this pilot. A second Streamlit Community Cloud app must be created from branch `security/clerk-hobby-test-pilot` using the page entry point `pages/11_Clerk_Auth_Pilot.py` or the repository's normal main entry with page discovery. In that new app only, set the server-side Secret:

```toml
CLERK_TEST_AUTHORIZED_PARTIES = "https://YOUR-NEW-TEST-APP.streamlit.app"
```

Replace the placeholder with the exact new test app origin. Do not reuse or modify the live production app's configuration. Until that separate app exists and its exact origin is pinned, the Clerk page deliberately fails closed with a missing-authorized-party message.

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

## Current verified status

- Clerk `Reject compromised passwords` is saved as `On` in the Development instance.
- Clerk's Supabase integration shows `Enabled`.
- Supabase Third-Party Auth shows Clerk as `Enabled` with issuer/domain `https://dear-hermit-1240.clerk.accounts.dev`.
- Test project status is `ACTIVE_HEALTHY`.
- Both pilot migrations are applied and present in test migration history.
- Post-migration read-only verification confirms `anon_select=false`, authenticated CRUD grants are true, RLS is true, and pilot row count is zero.
- The existing Supabase Security Advisor warnings remain: the exposed `public.cloudflare_worker_admin_dispatch(...)` SECURITY DEFINER execute warning and the native Supabase Auth leaked-password-protection warning. Neither was modified by this pilot. Clerk's HIBP protection protects Clerk-managed passwords; it does not turn on HIBP for the native Supabase Auth endpoints.
- Current branch head: `a3e7d98c431adb1c8f5b08ec81698c35bd927f7e`.
- Current AI Council CI run on this exact head passed: **1042 passed, 2 skipped**; release-candidate ZIP integrity and SHA-256 sidecar verification passed. Run: https://github.com/Mamoussa1966/free-chat-app/actions/runs/42829437550
- Current Supabase RLS database workflow on this exact head passed: all **54 pgTAP tests across 3 SQL test files** passed, including the isolated Clerk issuer/subject RLS suite. Run: https://github.com/Mamoussa1966/free-chat-app/actions/runs/42829437437
- The hosted test-project schema/RLS checks were also verified independently after applying the two pilot migrations; `anon` has no table SELECT privilege and the pilot table remains empty.
- No real Clerk session token has yet been accepted by a deployed Streamlit test page. A separate Streamlit test deployment is still required because the live production origin is explicitly excluded. No real external two-account test or live native Supabase Auth token bypass test has yet been executed.
- No production schema, secrets, Auth configuration, Cloudflare Worker, deployment, or AI provider call was changed.

## Official references

- Clerk password protection: https://clerk.com/docs/guides/secure/password-protection-and-rules
- Clerk pricing: https://clerk.com/pricing
- Supabase Clerk integration: https://supabase.com/docs/guides/auth/third-party/clerk
- Supabase Third-Party Auth and restrictions: https://supabase.com/docs/guides/auth/third-party/overview
- Supabase custom OIDC requirements and issuer restrictions: https://supabase.com/docs/guides/auth/third-party/custom-oidc
- authentik password policy: https://docs.goauthentik.io/customize/policies/types/password/
- Cloudflare Containers pricing: https://developers.cloudflare.com/containers/platform/pricing/
