# Clerk Hobby isolated authentication pilot

**Status:** Draft / test-only. No production rollout is authorized by this document.
**Base:** `gitops-v0.4-final` at `b4883ff5f33aa721c42909a2b09a2f2baf8325e8`.
**Test Supabase project:** `ai-council-storage-test` (`pidcepvwsezdrlhxqksg`, `ap-south-1`).
**Production Supabase project and Cloudflare Worker Admin:** explicitly out of scope.

## Decision

Use a dedicated Clerk Hobby application/instance as the candidate end-user identity provider for the isolated pilot. The choice is based on the current constraints:

- $0 plan with no credit card requirement and a published 50,000 monthly retained-user limit per app.
- Clerk's compromised-password protection checks new and changed passwords against Have I Been Pwned, and checks a correct password at sign-in. A breached password cannot be set; a discovered compromised password triggers the reset flow.
- Supabase documents a first-party Clerk Third-Party Auth integration. The integration uses Clerk session JWTs and RLS; do not use the legacy shared-Supabase-JWT-secret template.
- Clerk Hobby does not include production MFA. Therefore this pilot must not replace or weaken the existing Supabase Auth AAL2 path used by Cloudflare Worker Admin.

This is the best operational fit **only under the currently verified constraints** (hosted service, strict $0, direct Supabase integration, HIBP). It is not a universal claim that Clerk is the strongest identity platform. A self-hosted authentik deployment offers HIBP plus MFA, but would require an independently hosted, continuously available Postgres-backed service. Cloudflare Containers are not available on the Workers Free plan. Stytch is a credible alternative, but its published Supabase partner sample signs a Supabase-format JWT with the project's signing secret; that legacy pattern is not acceptable for this pilot. Supabase's current third-party-auth path requires an external OIDC issuer with asymmetric JWT signing and JWKS.

## Existing schema constraints discovered on the test project

The existing `public.council_conversations` table is not directly compatible with Clerk subjects:

- `owner_id` is `uuid NOT NULL REFERENCES auth.users(id)`.
- Its existing trigger and RLS policies call `auth.uid()`, which casts the JWT `sub` claim to UUID.
- Clerk user subjects are opaque text identifiers, not Supabase Auth UUIDs.

Do not cast, truncate, hash, or otherwise synthesize a UUID from a Clerk subject. Do not remove the existing FK, trigger, or policies as part of this pilot.

The pilot must use a separate test-only table whose owner identity is the exact pair `(issuer, subject)`, both stored as text. Its RLS policies must compare both claims to `auth.jwt()`. The issuer must be pinned to the exact Clerk test-instance issuer; it must never be accepted from a row supplied by the client.

## Non-negotiable security properties

1. Only the isolated Supabase test project may be registered with the Clerk test instance.
2. The Clerk pilot data table must accept only JWTs whose `iss` equals the pinned Clerk test issuer and whose `sub` equals the row owner.
3. Use a **restrictive** RLS policy for each data operation. A permissive policy that accepts either Supabase Auth or Clerk is not an acceptable no-bypass control.
4. A native Supabase Auth JWT must fail to read, insert, update, and delete pilot rows, even if its `role` claim is `authenticated`.
5. Clerk user A must not read, update, delete, or insert rows as user B; user B must not access user A's rows.
6. No service-role key or Supabase signing secret may be placed in the Streamlit client, browser, Clerk dashboard, or repository.
7. No raw password, password hash, access token, refresh token, or session JWT may be written to logs or conversation history.
8. Do not write raw Clerk session JWTs into browser localStorage. Let the Clerk browser SDK manage its session; pass a short-lived token to the server only when a request needs it.
9. The existing Cloudflare Worker Admin authorization flow and its Supabase Auth AAL2 checks remain unchanged and separately tested.
10. Production URLs, production secrets, production database schema, production RLS, and Worker configuration remain unchanged throughout the pilot.

## Pilot implementation sequence

### Gate 0 — external Clerk test instance

Create one dedicated Clerk test application/instance (not a production instance). Verify in its Dashboard:

- `Reject compromised passwords` is enabled.
- Password protection remains enabled for creation, password change, and sign-in.
- The instance's exact issuer/domain and publishable key are recorded in test-only Streamlit Secrets.
- The Supabase integration is activated using Clerk's current native integration (not a JWT template that shares the Supabase signing secret).

No credentials belong in Git. The publishable key is public configuration; any Clerk secret key remains server-side if later shown to be necessary. Never request or store a Supabase service-role key.

### Gate 1 — isolated Supabase trust

Register the exact Clerk test issuer in the test project's Authentication > Sign In / Providers > Third-Party Auth integration. Confirm the JWT contains `role: authenticated`.

Prepare a **separate test-only** conversation table, with a composite owner identity (`issuer`, `subject`) and RLS restrictions pinned to the Clerk test issuer. Keep the existing UUID-backed table untouched until the pilot proves the full replacement path. Do not apply the migration until the issuer is known and the complete SQL has passed local review.

### Gate 2 — Streamlit authentication adapter

Add an isolated Clerk auth adapter behind an explicit test-only feature flag. Fail closed unless the configured Supabase URL exactly equals the known test project URL and both the Clerk issuer and public configuration match the pilot allowlist.

The adapter must verify the JWT signature using Clerk's published JWKS, and validate issuer, expiry, subject, authorized party/audience, and the `authenticated` role. It must reject unknown `kid`, unsupported algorithms, malformed claims, expired tokens, and issuer mismatch. A decoded but unverified JWT payload must never be treated as an authenticated identity.

The browser component must use Clerk's supported browser SDK and retrieve short-lived session tokens; token refresh and Streamlit reruns must be covered by tests. No authentication request may call an AI model provider.

### Gate 3 — no-bypass and isolation acceptance

Use two disposable Clerk test accounts (A and B) and the existing test Supabase Auth account(s):

- A can create/read/update/delete only its own pilot rows.
- B cannot read/update/delete A's rows and cannot insert a row claiming A as owner.
- A native Supabase Auth JWT cannot read/insert/update/delete any pilot row.
- A token with a wrong issuer, missing `role`, expired `exp`, unknown `kid`, or altered signature is rejected.
- A compromised test password is rejected during set/change; a known test-only breached password is caught at sign-in and forced through the supported reset path.
- An unavailable or malformed HIBP-dependent response must not create a usable weak-password path; test this as provider behavior rather than implementing a second bypass.
- Sign-out, token renewal, browser refresh, account switching, and user data clearing are checked.
- The separate Cloudflare Worker Admin Supabase AAL2 flow is verified unchanged; no production Worker calls or configuration edits are part of this pilot.

Where applicable, test the same issuer restrictions for Storage, Realtime, and Edge Functions—not only PostgREST. No broad success claim is allowed until every service actually used by the application has been checked.

## Stop conditions

Stop and do not expand the pilot if:

- Clerk requires payment or enables billable overage for the selected setup.
- The instance cannot keep compromised-password protection enabled on Hobby.
- The test issuer cannot be registered as an asymmetric Supabase third-party issuer.
- The Streamlit flow requires a long-lived token in browser storage or a privileged key in the browser.
- The no-bypass tests permit a native Supabase Auth JWT to access pilot conversation data.
- Any change would require weakening Cloudflare Admin AAL2.
- Any step unexpectedly targets the production Supabase ref or production Worker.

## Current execution status

- Confirmed the Supabase test project is `ACTIVE_HEALTHY` in `ap-south-1`.
- Read-only inspection confirmed the current UUID/FK-backed conversation table and its four owner-scoped RLS policies.
- No test or production database schema has been changed for this pilot.
- No Clerk application has been created or connected yet. The exact Clerk test issuer and publishable key are required before registering the issuer and compiling the final RLS allowlist.
- No production merge, deployment, migration, secret change, provider API call, or billing action has occurred.

## Official references

- Clerk password protection: https://clerk.com/docs/guides/secure/password-protection-and-rules
- Clerk pricing: https://clerk.com/pricing
- Supabase Clerk integration: https://supabase.com/docs/guides/auth/third-party/clerk
- Supabase custom OIDC requirements and issuer restrictions: https://supabase.com/docs/guides/auth/third-party/custom-oidc
- authentik password policy: https://docs.goauthentik.io/customize/policies/types/password/
- Cloudflare Containers pricing: https://developers.cloudflare.com/containers/platform/pricing/
- Stytch partner example: https://supabase.com/partners/stytch
