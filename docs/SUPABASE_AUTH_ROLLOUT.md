# Supabase Auth rollout gate

This feature is intentionally opt-in. The Streamlit application remains on its existing session-only behavior unless all three settings are present and Auth is explicitly enabled.

## Streamlit Community Cloud Secrets

Set these values only in the app's Secrets settings:

```toml
SUPABASE_AUTH_ENABLED = "false"
SUPABASE_URL = "https://YOUR_PROJECT_REF.supabase.co"
SUPABASE_PUBLISHABLE_KEY = "sb_publishable_..."
```

Use the project's publishable key (or legacy anon key only for an older project). Never use `service_role`, `sb_secret_...`, a database password, or an administrative token in Streamlit. Do not commit real values to GitHub.

Leave `SUPABASE_AUTH_ENABLED` set to `false` until the live acceptance test below passes. Then change it to `"true"` to turn on the login screen and owner-scoped storage.

## Identity and storage behavior

- Sign-up and password login use Supabase Auth's HTTPS REST API.
- The account subject is obtained from the authenticated `GET /auth/v1/user` response, not from a user-supplied email or an unverified JWT decode.
- During a live Streamlit WebSocket session, access and refresh tokens remain in server-side `st.session_state`; the access token is sent as the user bearer token and the publishable key is only the project API key.
- When `SUPABASE_SESSION_ENCRYPTION_KEY` is configured, the app stores only a Fernet-encrypted session envelope in browser localStorage to restore a new Streamlit connection. The encryption key never leaves Streamlit Secrets; the browser component does not receive it. Browser storage is JavaScript-readable, so this is not equivalent to an HttpOnly server-set cookie. Keep untrusted HTML/JavaScript out of the app.
- Restoration revalidates the session through Supabase Auth and checks the configured project issuer and user subject. Missing or invalid encryption keys disable cross-connection restoration without disabling ordinary login.
- A session is refreshed through `/auth/v1/token?grant_type=refresh_token` near expiry and periodically revalidated through Auth; rotated session state is re-encrypted for browser persistence.
- Each repository object is bound to one `AccountIdentity(issuer, subject)`; RLS remains the database authorization boundary.
- Canonical identity history and a bounded presentation/history snapshot are written only after a request lifecycle completes. Save errors are shown as errors and are not reported as durable success.
- Signing out or switching account clears the previous user's Streamlit session state. Only RLS-visible conversation IDs are loaded.
- Sign-up may require email confirmation. If Auth does not return a session during sign-up, the UI asks the user to confirm the email and then sign in.

## Required live acceptance test

Use two dedicated, disposable, email-confirmed test accounts in the isolated project `ai-council-storage-test`. Do not put their passwords in the repository, Streamlit app secrets, logs, or this conversation.

Run `scripts/test_supabase_auth_postgrest_live.py` in a trusted runner with the following runtime environment variables:

- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY`
- `SUPABASE_TEST_USER_A_EMAIL`
- `SUPABASE_TEST_USER_A_PASSWORD`
- `SUPABASE_TEST_USER_B_EMAIL`
- `SUPABASE_TEST_USER_B_PASSWORD`

Use the manual workflow in two phases:

1. Choose `signup` using two **fresh disposable email addresses** controlled by the project owner. The workflow calls the real Auth sign-up endpoint and verifies the session identity if Supabase issues a session immediately. If confirmation is required, it reports that no session was issued; open both confirmation emails before the next phase.
2. Choose `auth-postgrest` after both accounts are confirmed. This performs real password login and refresh for each user, verifies distinct subjects using Auth's `/user` endpoint, and exercises the actual Data API. It creates a temporary conversation row owned by A, verifies B cannot read/list/update/delete it, checks that A's content remains unchanged, and removes the temporary row in a cleanup block.

The test never bypasses email confirmation and never uses a service-role key. Auth test users may remain in the dedicated test project and should be removed manually after acceptance if no longer needed. Unit tests also cover the registration response and the pending-confirmation branch.

## Exposed schemas and Data API

The migration grants `USAGE` on `public` and explicitly grants SELECT/INSERT/UPDATE/DELETE on `public.council_conversations` only to `authenticated`, while RLS is enabled and forced. The SQL role grants alone cannot reveal the hosted PostgREST `db-schemas` configuration. The live test's authenticated REST requests are the end-to-end check that `public` is exposed to the Data API and that the table is reachable with the user's bearer token. If the live REST test reports an API/schema error, do not enable Auth; verify the project's API settings and exposed schemas in the dashboard first.

Supabase's published rollout says explicit grants are required for new tables to be exposed via Data API as the October 30, 2026 change is applied: https://supabase.com/changelog/45329-breaking-change-tables-not-exposed-to-data-and-graphql-api-automatically
