# Supabase storage and authentication decision

**Decision date:** 2026-10-23  
**Decision:** Use Supabase Auth + PostgreSQL for the first account-owned durable-storage slice.  
**Current implementation scope:** SQL migration, a user-JWT/PostgREST adapter, and automated isolation/contract tests only. This PR does not wire the adapter into Streamlit or create a Supabase project.

## Why Supabase

The Council needs verified account identity, durable relational storage, and a database-enforced boundary between users. Supabase provides authentication and PostgreSQL in one service and supports per-operation Row Level Security (RLS) policies using `auth.uid()`. That reduces the number of independently configured identity/storage services.

This is a decision for the next implementation slice, not a claim that the Free plan is suitable for a production SLA.

## Free-tier comparison checked on 2026-10-23

| Candidate | Relevant free allowance / strengths | Material limitations for this project |
| --- | --- | --- |
| Supabase | $0 plan; PostgreSQL; Auth; documented RLS; 500 MB database per project; 50,000 monthly active users; 5 GB egress; two free projects. | Free projects can pause after around one week of inactivity. Automatic database backups are not included in Free. Storage and egress quotas still apply. |
| Neon + separate Auth | PostgreSQL; free allowance documented as 0.5 GB storage, 100 CU-hours per project per month, 5 GB public transfer and a six-hour instant-restore history limit. | Requires a separately selected and secured identity provider; adds a cross-service identity mapping and operational boundary. |
| Firebase | Spark no-cost plan; authentication options; Firestore no-cost allowance includes 1 GiB stored data and daily read/write/delete quotas. | Document/NoSQL access patterns differ from the Council's canonical snapshot contract; export/restore and data-model migration would need a different adapter. |

Official references:
- Supabase pricing: https://supabase.com/pricing
- Supabase free project pausing: https://supabase.com/docs/guides/platform/free-project-pausing
- Supabase backups: https://supabase.com/docs/guides/platform/backups
- Supabase RLS: https://supabase.com/docs/guides/database/postgres/row-level-security
- Supabase Auth: https://supabase.com/docs/guides/auth
- Neon Free plan limits: https://neon.com/docs/introduction/plans
- Firebase pricing: https://firebase.google.com/pricing
- Firebase pricing plans: https://firebase.google.com/docs/projects/billing/firebase-pricing-plans

## Security model for the adapter

1. The adapter uses the Supabase public anon/publishable key plus the currently signed-in user's access token. It must never accept or use a `service_role` key or a database-owner password.
2. Each public adapter operation validates the token through Supabase Auth's `/auth/v1/user` endpoint and verifies that the supplied stable identity (`issuer`, `subject`) matches the authenticated user.
3. Every REST operation is authenticated by the same user's JWT. PostgreSQL RLS separately enforces `auth.uid() = owner_id` for SELECT, INSERT, UPDATE, and DELETE.
4. REST queries also filter by `owner_id`; this is defense in depth, not a replacement for RLS.
5. The database uses a globally unique `conversation_id` primary key to prevent a second account from taking over an existing ID. Row contents also bind to the canonical conversation ID and contract.
6. The canonical JSON snapshot is checksummed. The adapter verifies it on read, rejects malformed/dangling Message → Request → Round links using the shared canonical envelope, and prevents silent history removal or rewriting established identity fields.
7. API responses and exception messages never include access tokens, anon keys, snapshot contents, or raw server error bodies. The user JWT is sent only in the HTTP Authorization header and is not persisted.
8. No UI/application wiring, token refresh/session storage, login form, Secrets, or provider code is added in this phase.

## Backup, restore, privacy, and portability

- Supabase Free does not include automatic database backups. Before enabling user conversations, the project owner must establish a recurring encrypted export and off-provider/offline retention procedure, and demonstrate a restore drill. An export stored only in the same Supabase project is not an independent backup.
- Free projects may pause after inactivity; treat reactivation and downtime as a known limitation rather than promising uninterrupted production availability.
- Do not store provider API keys, access tokens, raw credential payloads, or hidden operational secrets in canonical conversation records.
- Keep any database connection strings and Auth secrets out of Git. The adapter code requires a public anon key and a current user's short-lived access token at runtime; both must be provided through a secure server-side configuration/session flow in a later PR.
- PostgreSQL and JSON snapshots can be exported with standard PostgreSQL tooling / Supabase's documented dump workflow. The adapter is behind the repository Protocol so a later migration does not require rewriting Council orchestration.
- Review data region, retention, privacy terms, and account deletion behavior in the Supabase Dashboard before real users are invited.
- The Free plan and its limits can change. Re-check official pricing/backup documentation before public launch.

## Implementation steps and acceptance gates

1. Create the schema migration with RLS enabled and separate policies for each operation.
2. Add a PostgREST adapter bound to a verified user JWT; do not wire it into `main.py` or `app.py`.
3. Test two distinct user identities against a shared fake PostgREST service: no cross-account read/list/update/delete, no owner takeover, stable immutable IDs, corruption detection, idempotent save, and append-only history.
4. Run SQL policy tests with Supabase local/test tooling before deploying the migration to any real project.
5. Require `CI / regression-and-package` to pass on the PR head.
6. Only in a future PR, select and configure a Supabase project, implement/login token lifecycle, run a real two-user RLS smoke test and a restore drill, then decide whether application wiring is safe.

## Not in scope

- Creating a Supabase project or accepting terms on the owner's behalf.
- Adding or changing GitHub/Streamlit Secrets.
- Enabling authentication or durable user storage in the deployed Council.
- Putting a service-role key into any source file, test, workflow, client-side UI, or log.
- Claiming cross-restart production persistence before a real project and restore drill have been verified.
