# Storage and identity provider decision — AI Council

**Decision date:** 2026-10-23  
**Decision:** Supabase Free for the first isolated database adapter and later authentication integration.  
**Scope:** Architecture and adapter only. This decision does not provision a project, add deployment secrets, enable sign-in, or connect the Streamlit UI.

## Requirements carried forward

- Free tier only: no paid fallback or surprise pay-as-you-go dependence.
- PostgreSQL for canonical Message → Request → Round snapshots and future migration flexibility.
- Database-enforced ownership isolation, not UI-only checks.
- Authentication identity is an immutable issuer + subject pair; never use email or display name as a database primary identity.
- Tests must use two accounts and prove that one account cannot read, list, change, or delete another account's conversations.
- The current canonical store, provider identities, `VERSION.txt`, release manifests, and deployed Streamlit behavior must remain unchanged until separate acceptance.

## Options compared

| Capability | Supabase Free | Firebase Spark (Firestore + Auth) |
|---|---|---|
| Authentication and database | Built-in Supabase Auth plus managed PostgreSQL | Firebase Authentication plus Firestore |
| Database model | Relational SQL and JSONB; fits canonical records and explicit migration scripts | Document database; workable, but relational integrity across Message / Request / Round would need more application-level modeling |
| Authorization | PostgreSQL Row Level Security (RLS) policies can bind row ownership to the signed-in JWT via `auth.uid()` | Firestore Security Rules can enforce document ownership; rules and data shape need their own design |
| Published free quota checked on this date | Pricing page lists 50,000 monthly active users, 500 MB database size, 5 GB egress, and 1 GB file storage; two free projects | Firestore pricing lists 1 GiB stored data, 50,000 reads/day, 20,000 writes/day, and 20,000 deletes/day; most Firebase Auth providers are no-cost on Spark, with a documented limit of 3,000 daily active users for most providers |
| Backups and recovery | Automatic daily database backups and PITR are not included in Free. Supabase recommends regular logical exports and off-site backups | Firestore backup, point-in-time recovery, and restore operations are not included in its free quota and require billing |
| Availability constraint | Free projects may be paused after a week of low activity | No Supabase-style one-week pause is claimed here; quotas and product-specific limits still apply |
| Portability | PostgreSQL schema/data can be exported and migrated using standard PostgreSQL tools | Data can be exported, but conversion from document collections to relational canonical records requires a migration plan |

## Why Supabase was selected

Supabase has the strongest fit for the current repository because it combines PostgreSQL, Auth, and row-level policies. The canonical repository already represents one conversation with messages, requests, and rounds, and our requirements emphasize preserving explicit identity links and rejecting conflicting history. PostgreSQL makes those constraints, JSONB snapshots, versioned SQL migrations, and a future export path straightforward.

The adapter in this PR deliberately uses the publishable key plus the authenticated user's access token. It must not use a Supabase secret/service-role key: such keys bypass RLS. Database policies and triggers remain authoritative even when Python performs defensive pre-validation.

## Free-tier risk acceptance and mitigations

Supabase Free is appropriate for a no-payment prototype and a bounded early release, but it is **not yet a complete production backup/SLA plan**:

1. A Free project may pause after 7 days of low activity. Recovery requires action in the Supabase dashboard.
2. Automatic backups and PITR are not included on Free. Before accepting any user data, establish a repeatable logical export and an off-site copy under the project owner's control. A backup is not considered proven until a restore test succeeds.
3. Monitor database usage and egress before approaching the published limits. Fail safely if storage is unavailable or quota is exhausted; never report an uncommitted write as successful.
4. Keep production identity, migrations, and data access separate from test fixtures. No user data or credentials go into the Git repository.
5. Do not enable production authentication until email delivery/rate limits, session expiry, account recovery, sign-out, and authorization tests have been reviewed.

## Implementation sequence

1. This PR: isolate a Supabase/PostgREST adapter and SQL migration with RLS plus append-only canonical identity validation.
2. Run Python adapter contract tests using two independent test identities and a fake HTTP boundary; include database-level RLS tests for later execution against a local Supabase/PostgreSQL test instance.
3. Require `CI / regression-and-package` to pass; do not wire adapter into `main.py` or `app.py`.
4. Separately create/configure a Supabase Free project only when the owner is ready; apply migrations in that project and perform a real two-account isolation test.
5. Add an identity adapter that verifies the Supabase Auth session and binds the JWT to `AccountIdentity(issuer, subject)`.
6. Design off-site export/restore and successfully test a restore before production data is accepted.
7. Only then propose a separate PR for application wiring and a gated rollout.

## Official sources checked 2026-10-23

- Supabase Free pricing and published quotas: https://supabase.com/pricing
- Supabase Auth integration: https://supabase.com/docs/guides/auth
- Supabase Row Level Security policies and ownership guidance: https://supabase.com/docs/guides/database/postgres/row-level-security
- Supabase Free-tier pausing behavior: https://supabase.com/docs/guides/platform/free-project-pausing
- Supabase backups and manual logical-export recommendation for Free: https://supabase.com/docs/guides/platform/backups
- Supabase secure-data guidance and warning about secret keys bypassing RLS: https://supabase.com/docs/guides/platform/secure-data
- Firebase Spark plan: https://firebase.google.com/docs/projects/billing/firebase-pricing-plans
- Firestore free quota and backup/restore billing: https://firebase.google.com/docs/firestore/pricing
- Firebase Auth Spark usage limits: https://firebase.google.com/docs/auth

## Explicit non-goals

- No production Supabase project is created by this PR.
- No Streamlit Secrets are changed or requested by this PR.
- No sign-in UI is introduced.
- No local file adapter is used as a durable hosted database.
- No provider seat, model selection, Free Cascade, frozen release identity, or production CI workflow is changed.
