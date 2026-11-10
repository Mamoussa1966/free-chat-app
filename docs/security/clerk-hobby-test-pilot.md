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

## Applied isolated test migration

The test project has the migration:

`20261110123054_clerk_auth_pilot_isolated_rls`

Repository migration file:
`supabase/migrations/20261110123054_clerk_auth_pilot_isolated_rls.sql`

It creates only `public.clerk_auth_pilot_records`, a separate, currently empty test table. The table stores the Clerk `sub` claim as text. Because this pilot pins a single issuer, the issuer is enforced as a fixed literal in a **restrictive** RLS policy rather than stored redundantly per row.

The migration:
- Enables RLS on the test table.
- Grants table CRUD privileges only to the `authenticated` database role.
- Requires `auth.jwt()->>'iss'` to equal exactly `https://dear-hermit-1240.clerk.accounts.dev` through a restrictive `FOR ALL` policy.
- Requires each operation's permissive policy to match `owner_subject` to the token's `sub`.
- Does not modify `public.council_conversations`, `private_cloudflare.worker_admin_operators`, Supabase Auth users, or any production project.

The migration is applied and recorded in the test project's migration history. Its SQL is also tracked in this PR branch for review/reproducibility. No test rows have been inserted into the hosted test project.

## Database RLS test coverage

Added `supabase/tests/clerk_auth_pilot_rls.test.sql` to the local Supabase pgTAP workflow. It verifies:

- RLS is enabled and `anon` lacks SELECT privilege.
- Clerk issuer + subject A can insert/read its own record.
- Clerk user B cannot read, modify, delete, or spoof ownership of A's record, but can insert/read its own record.
- A token with the native Supabase Auth issuer cannot read or insert into the Clerk pilot table.
- A token with a wrong issuer cannot read or insert.
- User A's original data remains unchanged after B's attempted modification/deletion.

The same workflow applies versioned migrations in a disposable local Supabase stack and runs `supabase test db --local`. These are local database JWT-claim tests, not proof of a real browser sign-in or a live Clerk session token. The live external-token acceptance tests below remain required.

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
- Migration `20261110123054_clerk_auth_pilot_isolated_rls` is present in the test database migration history.
- Read-only verification confirms the pilot table exists, RLS is enabled, the exact restrictive issuer policy and four owner policies exist, and authenticated CRUD privileges are present.
- Pilot table row count is zero. Existing conversation table row count remains zero in this test project; its schema, FK, and four existing owner policies were not modified.
- Existing Supabase Security Advisor warnings remain: the exposed `public.cloudflare_worker_admin_dispatch(...)` SECURITY DEFINER execute warning and the native Supabase Auth leaked-password-protection warning. Neither was modified by this pilot. Clerk's HIBP protection protects Clerk-managed passwords; it does not turn on HIBP for Supabase's native Auth endpoints.
- No real Clerk session token, native Supabase bypass attempt, two-account external-token test, or Streamlit Clerk sign-in has yet been executed.
- No production schema, secrets, Auth configuration, Cloudflare Worker, deployment, or AI provider call was changed.

## Official references

- Clerk password protection: https://clerk.com/docs/guides/secure/password-protection-and-rules
- Clerk pricing: https://clerk.com/pricing
- Supabase Clerk integration: https://supabase.com/docs/guides/auth/third-party/clerk
- Supabase Third-Party Auth and restrictions: https://supabase.com/docs/guides/auth/third-party/overview
- Supabase custom OIDC requirements and issuer restrictions: https://supabase.com/docs/guides/auth/third-party/custom-oidc
- authentik password policy: https://docs.goauthentik.io/customize/policies/types/password/
- Cloudflare Containers pricing: https://developers.cloudflare.com/containers/platform/pricing/
