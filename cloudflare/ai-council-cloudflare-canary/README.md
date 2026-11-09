# AI Council Cloudflare Canary

This is a deliberately isolated, health-only Cloudflare Worker used to establish
a reproducible deployment path for the AI Council project without TinyFish or
a remote browser session.

## Security boundary

- Worker name: `ai-council-cloudflare-canary`
- Runtime surface: `GET /health` and `HEAD /health` only
- No secrets, environment variables, KV, D1, R2, Durable Objects, service
  bindings, external fetches, user data, or database connections.
- No Worker deletion endpoint or administrative operation.
- Observability is initially disabled to avoid generating unnecessary events.
- The Worker is separate from the Supabase administrator gateway and does not
  grant the Streamlit application access to Cloudflare.

## Cloudflare Workers Builds (preferred, no TinyFish)

Connect this project to Cloudflare's native Git integration:

1. Open the account's **Workers & Pages** page.
2. Select **Create application** and choose **GitHub**.
3. Authorize the Cloudflare Workers and Pages GitHub App for the
   `Mamoussa1966/free-chat-app` repository only.
4. Select branch `gitops-v0.4-final`.
5. Set the project root directory to
   `cloudflare/ai-council-cloudflare-canary`.
6. Build command: `npm install && npm run check`.
7. Deploy command: `npm run deploy`.
8. Keep preview builds disabled for the initial canary. Enable them only after
   the first production-branch deployment has been verified.
9. Review the API token selected under **Settings > Builds** before keeping
   the integration active.

Cloudflare Workers Builds runs the build and deploy commands when a commit is
pushed to the connected production branch. It can report build status in
GitHub, avoiding TinyFish, a cloud-browser wallet, and a Cloudflare credential
in GitHub Actions.

## Token handling

Cloudflare documents that its automatically generated Workers Builds token
starts with broad permissions for Workers Scripts, KV, R2, routes, and certain
account/user read scopes. Do not treat that automatically generated token as
the desired long-term least-privilege credential.

After the canary Worker has been created and its exact identity is known:

1. Create or select a user-owned API token with **Individual Workers Editor**
   scoped to this Worker only, where supported by the Workers Builds token
   selector.
2. Replace the broad bootstrap/build token with the scoped token.
3. Revoke the temporary broad token after confirming a successful build with
   the scoped token.
4. Do not copy either token into source code, GitHub repository files, or
   Streamlit secrets.

The separate Supabase production gateway still requires its own narrowly
scoped Cloudflare credential in Supabase Vault before its Cloudflare API
operations can be activated. Workers Builds does not populate that Vault
secret and does not enroll a Supabase operator.

## Verification after connection

- Confirm the Worker name is exactly `ai-council-cloudflare-canary`.
- Confirm the selected account ID is
  `1171975142d29fc55425b752629bb8bd`.
- Confirm the build ran from the `gitops-v0.4-final` branch and this root
  directory.
- Request `https://ai-council-cloudflare-canary.electroplating-engineer.workers.dev/health`
  and verify HTTP 200 with `ok: true` and the expected release ID.
- Confirm a non-`/health` path returns 404 and a non-GET/HEAD method on
  `/health` returns 405.
- Confirm the build token is restricted to the one Worker after bootstrap.

## Free-plan note

Cloudflare currently documents 3,000 Workers Builds minutes per month for the
Free plan. Worker request limits are separate; the account overview currently
shows a 100,000-request daily allowance. Stay within those published quotas
and do not enable paid Workers features for this canary.
