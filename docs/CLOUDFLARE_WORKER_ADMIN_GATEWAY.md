# Cloudflare Worker Admin Gateway

## Status and environment boundary

This implementation is a candidate for review on
`security/cloudflare-admin-authenticated-gateway-20261109`.

- The authenticated Edge Function and gateway migration were deployed/applied to
  `ai-council-storage-test` only.
- The gateway intentionally does not expose Worker deletion. It is designed to
  run with Cloudflare's per-Worker `Individual Workers Editor` permission,
  which supports reading, version upload, deployment and metadata updates for
  selected existing Workers but does not grant Worker creation/deletion.
- No Edge Function was deployed to Supabase Production by this change.
- No Production secret, Cloudflare token, Worker allow-list row, or Worker was
  created or modified by this change.
- The operator allow-list is deliberately empty by default.
- Cloudflare Worker operations remain unavailable until an explicit user is
  enrolled by a database owner and each target Worker is separately registered.

## Request path

`Streamlit server` → `cloudflare_worker_admin_client.py` → authenticated
Supabase Edge Function `cloudflare-worker-admin` → public RPC
`cloudflare_worker_admin_dispatch` → private per-Worker administration
functions → Cloudflare API using the Vault token.

The Streamlit client sends only:
- the project's publishable (or legacy anon) key in `apikey`;
- the signed-in user's short-lived JWT in `Authorization: Bearer`;
- the operation name, a target Worker name, a bounded operation payload, and
  an optional exact confirmation phrase.

The Edge Function uses a publishable/legacy anon key only, validates that
the bearer key is a signed-in user's JWT by calling Supabase Auth, and forwards
the same user JWT to the SQL gateway. It never reads a Supabase secret/service
key or the Cloudflare API token.

It does not accept a Cloudflare token, Supabase secret key, service-role key,
arbitrary HTTP method, arbitrary Cloudflare API path, or raw SQL from the caller.

## Authentication and authorization

1. Supabase Edge Function configuration requires `verify_jwt = true`.
2. The Edge Function independently asks Supabase Auth to validate the caller's
   bearer token using `auth.getUser(accessToken)`.
3. The SQL dispatcher requires a non-anonymous `authenticated` user identity.
4. The user's UUID must appear in `private_cloudflare.worker_admin_operators`
   with `enabled = true`.
5. The requested action must appear in that user's `allowed_actions`.
6. Every operation except read-only `list` requires JWT assurance level
   `aal2` (MFA).
7. The dispatcher's operation switch accepts a fixed set of actions and calls
   only the corresponding private SQL function. It does not expose the
   internal HTTP helper.
8. The operator table is RLS + FORCE RLS protected and is accessible only to
   the database owner role. The dispatcher is a narrowly scoped
   `SECURITY DEFINER` function with a fixed search path; it does not grant
   clients access to the operator table or private Cloudflare schema.
9. Anonymous and service-role callers have no execute grant on the dispatcher.
   Authenticated users can execute only the dispatcher, not the private
   administration functions or tables.

## Operator enrollment — manual, separate approval

No operator is enrolled by default. Do not add a user until the application
owner explicitly approves the exact Auth user UUID and action list. Every
operator action update must also identify an existing approving Auth user UUID.

Obtain the UUID from a trusted, verified Supabase Auth `/user` response for
the intended signed-in account. Do not infer it from an email address or
unverified JWT payload.

For the initial safest read-only enrolment, the database owner may use this
template in the intended environment after approval:

```sql
insert into private_cloudflare.worker_admin_operators
    (user_id, enabled, allowed_actions, created_by)
values
    ('<VERIFIED_AUTH_USER_UUID>'::uuid,
     true,
     array['inspect']::text[],
     '<DATABASE_OWNER_AUDIT_USER_UUID>'::uuid);
```

This template is documentation only. It has not been run in Production or
Test by this change. Replace both UUID placeholders only after independently
verifying their identities. Do not add `deploy` or `set_policy`
merely to make setup convenient. The insert is recorded automatically in the
append-only Worker audit table with the creator UUID and allowed actions.

To change an operator's actions, use an audited UPDATE and identify the
approving owner in `updated_by`:

```sql
update private_cloudflare.worker_admin_operators
   set allowed_actions = array['inspect']::text[],
       enabled = true,
       updated_by = '<VERIFIED_DATABASE_OWNER_AUTH_USER_UUID>'::uuid,
       updated_at = now()
 where user_id = '<VERIFIED_AUTH_USER_UUID>'::uuid;
```

Operator rows cannot be hard-deleted. Disable an operator instead, so
enrollment and policy history remains auditable.

Worker enrollment is separate. A Worker must first exist in the Cloudflare
account, be registered in the per-Worker allow-list, and receive only the
minimum operation set it needs. Production deletion remains prohibited by the
existing lower-level Worker policy. Any production deployment/rollback still
requires the exact confirmation phrase enforced by the private function.

## Exact operation names

- `list`
- `register`
- `refresh_versions`
- `update_metadata`
- `upload_version`
- `deploy`
- `rollback`
- `set_policy`

The lower-level private functions remain the final enforcement layer for
resource scope, environment, release identity, allowed operation and exact
confirmation. A successful HTTP response alone is not treated as proof of a
successful Cloudflare operation; callers must inspect the structured result.

## Audit trail

The audit table is append-only. The dispatcher attaches actor UUID, request
UUID and interface context to inserted audit rows. Denied requests from
authenticated callers are recorded without storing bearer tokens, Cloudflare
credentials or Worker source code. Successful private operations also retain
their operation-specific audit metadata.

Operator enrollment remains a database-owner action. It must be performed as
a separately approved change and verified after execution.

## Production Cloudflare API token — proposed least privilege

Do not reuse the broad token currently held in the Test Vault. Create a
separate account-owned API token for Production after a Worker has been
selected.

Use two narrowly separated Workers permission policies on that token:

1. **Workers product — Metadata Read-Only**: allows the bridge to list the
   account's Worker names and metadata. It does not permit viewing Worker
   source content or making changes.
2. **Individual Workers — Editor**: apply only to the explicitly selected
   existing Worker or Workers. Editor permits reading/updating/deploying
   existing Workers but does not permit creating or deleting Workers.

Do not grant product-level Workers Editor/Admin, Individual Workers Admin,
Workers Scripts Write as a broad account permission, or any Developer Platform
Admin role. Do not grant Billing, Account Settings, API Tokens, Secrets Store,
KV, R2, Workers AI, Tail, logs, DNS, Zone or User permissions.

Cloudflare's current permission model explicitly supports combining
product-level Metadata Read-Only with Editor on only selected Worker resources.
The List Workers API accepts Metadata Read-Only; version upload and deployment
accept Individual Workers Editor; partial metadata editing accepts Individual
Workers Editor. The Worker role documentation says Editor cannot create or
delete Worker resources. See:
- https://developers.cloudflare.com/workers/authorization/workers/
- https://developers.cloudflare.com/workers/authorization/
- https://developers.cloudflare.com/changelog/post/2026-09-15-granular-worker-permissions/
- https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/methods/list/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/create/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/deployments/methods/create/
- https://developers.cloudflare.com/api/go/resources/workers/subresources/beta/subresources/workers/methods/edit/

The current Cloudflare inventory is empty, so there is no existing Worker to
place in an Individual Workers Editor scope yet. A product-level
Metadata Read-Only policy can discover metadata without source access; after
the application owner selects or creates the specific Worker through the
normal Cloudflare Dashboard workflow, add Editor for that Worker only. Do not
widen the token to Admin just to enable creation.

Set a short initial expiry (for example, 30 days). Use an IP restriction only
if the production runtime has a verified stable outbound IP range; do not
guess or invent ranges.

The token must not be saved in Streamlit Secrets or GitHub Secrets. The
intended server-side destination is the Production project's Vault secret
`cloudflare_account_api_token`, after a separate explicit approval. This
branch has not created or saved a Production token.

## Verification completed in the isolated test project

- Migration applied to `ai-council-storage-test`.
- pgTAP gateway authorization tests passed (21 assertions).
- No `anon` execute grant on the dispatcher.
- No `service_role` execute grant on the dispatcher.
- `authenticated` has access only to the public dispatcher; private schema
  remains unavailable to client roles.
- The operator table is empty and the Worker allow-list is empty.
- Edge Function deployed with `verify_jwt = true`.
- Calling the Edge Function without a JWT returns HTTP 401.
- Calling the Edge Function with a malformed JWT returns HTTP 401.
- The gateway's delete operation is rejected as unsupported; delete-policy
  registration is rejected before reaching the private Worker functions.
- No Cloudflare administrative write, deploy or delete was attempted as part
  of the gateway-authentication tests.

## Remaining release gates

- Review the branch and pass CI before merging.
- Supabase Security Advisor reports one intentional
  `authenticated_security_definer_function_executable` warning for the
  public dispatcher. The only granted caller role is `authenticated`; the
  function is owner-executed with a fixed search path, verifies `auth.uid()`,
  requires an explicit operator row/action, and exposes no private schema
  grants. This is a deliberate narrow RPC boundary rather than a broad
  service-role bypass.
- Verify the Edge Function's runtime behavior after deploy with an
  independently issued test-user JWT, while the operator allow-list remains
  empty; the expected result is a sanitized 403, not an administrative action.
- Do not enroll an operator, add a Production Cloudflare token, deploy the
  Production Edge Function, or run Worker operations until each is approved
  as a separate change.
- Before future Production activation, compare the existing Production
  migration/function definitions to this branch and prepare a written
  deployment/rollback plan. Do not reapply the base migration blindly.
