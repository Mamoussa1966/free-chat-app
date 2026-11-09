import { createClient } from "npm:@supabase/supabase-js@2";

const OPERATIONS = new Set([
  "list",
  "register",
  "refresh_versions",
  "update_metadata",
  "upload_version",
  "deploy",
  "rollback",
  "set_policy",
]);

const MAX_BODY_BYTES = 300_000;
const MAX_PAYLOAD_BYTES = 280_000;

function json(data: Record<string, unknown>, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "Pragma": "no-cache",
    },
  });
}

function isPublishableOrLegacyAnon(value: string): boolean {
  if (value.startsWith("sb_publishable_")) return true;
  if (value.startsWith("sb_secret_")) return false;

  // Legacy anon keys are JWTs. Accept only a verified-format anon-role key;
  // never fall back to a service_role JWT.
  const parts = value.split(".");
  if (parts.length !== 3 || parts[1].length > 8192) return false;
  try {
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
    const payload = JSON.parse(atob(padded)) as { role?: unknown };
    return payload?.role === "anon";
  } catch {
    return false;
  }
}

function getPublishableKey(): string {
  const named = Deno.env.get("SUPABASE_PUBLISHABLE_KEYS");
  if (named) {
    try {
      const parsed = JSON.parse(named) as Record<string, unknown>;
      const selected = typeof parsed.default === "string" ? parsed.default : "";
      if (selected && isPublishableOrLegacyAnon(selected)) return selected;
    } catch {
      // Fail closed unless a separate publishable/anon key is configured.
    }
  }

  const standalone = Deno.env.get("SUPABASE_PUBLISHABLE_KEY") ?? "";
  if (standalone && isPublishableOrLegacyAnon(standalone)) return standalone;

  const legacy = Deno.env.get("SUPABASE_ANON_KEY") ?? "";
  if (legacy && isPublishableOrLegacyAnon(legacy)) return legacy;
  return "";
}

function isUuid(value: unknown): value is string {
  return typeof value === "string" &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}

Deno.serve(async (req: Request): Promise<Response> => {
  if (req.method !== "POST") {
    return json({ ok: false, code: "method_not_allowed" }, 405);
  }

  const contentType = req.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().includes("application/json")) {
    return json({ ok: false, code: "json_required" }, 415);
  }

  const authorization = req.headers.get("authorization") ?? "";
  if (!/^Bearer\s+\S+$/i.test(authorization)) {
    return json({ ok: false, code: "user_session_required" }, 401);
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? "";
  const publishableKey = getPublishableKey();
  if (!supabaseUrl || !publishableKey) {
    return json({ ok: false, code: "backend_configuration_unavailable" }, 503);
  }

  let rawBody: string;
  try {
    rawBody = await req.text();
  } catch {
    return json({ ok: false, code: "invalid_request_body" }, 400);
  }
  if (new TextEncoder().encode(rawBody).byteLength > MAX_BODY_BYTES) {
    return json({ ok: false, code: "request_too_large" }, 413);
  }

  let body: Record<string, unknown>;
  try {
    const parsed: unknown = JSON.parse(rawBody);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return json({ ok: false, code: "json_object_required" }, 400);
    }
    body = parsed as Record<string, unknown>;
  } catch {
    return json({ ok: false, code: "invalid_json" }, 400);
  }

  const operation = body.operation;
  const workerName = body.worker_name ?? null;
  const payload = body.payload ?? {};
  const confirmation =
    typeof body.confirmation === "string" ? body.confirmation : null;
  const requestId = isUuid(body.request_id) ? body.request_id : crypto.randomUUID();

  if (typeof operation !== "string" || !OPERATIONS.has(operation)) {
    return json({ ok: false, code: "unsupported_operation", request_id: requestId }, 400);
  }
  if (
    workerName !== null &&
    (typeof workerName !== "string" || !/^[a-z0-9][a-z0-9-]{0,62}$/.test(workerName))
  ) {
    return json({ ok: false, code: "invalid_worker_name", request_id: requestId }, 400);
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return json({ ok: false, code: "invalid_payload", request_id: requestId }, 400);
  }
  if (new TextEncoder().encode(JSON.stringify(payload)).byteLength > MAX_PAYLOAD_BYTES) {
    return json({ ok: false, code: "payload_too_large", request_id: requestId }, 413);
  }

  // Only a publishable/anon key is used here. The user's own JWT remains the
  // Authorization credential. No service-role/secret key is read or created.
  const supabase = createClient(supabaseUrl, publishableKey, {
    auth: {
      persistSession: false,
      autoRefreshToken: false,
      detectSessionInUrl: false,
    },
    global: { headers: { Authorization: authorization } },
  });

  const userAccessToken = authorization.slice(7).trim();
  const { data: userData, error: userError } = await supabase.auth.getUser(userAccessToken);
  if (userError || !userData?.user?.id) {
    return json({ ok: false, code: "invalid_user_session", request_id: requestId }, 401);
  }

  const { data, error } = await supabase.rpc("cloudflare_worker_admin_dispatch", {
    p_operation: operation,
    p_worker_name: workerName,
    p_payload: payload,
    p_confirmation: confirmation,
    p_request_id: requestId,
  });

  if (error) {
    const status = error.code === "42501" ? 403 : 400;
    return json(
      {
        ok: false,
        code: status === 403 ? "database_permission_denied" : "gateway_request_rejected",
        request_id: requestId,
      },
      status,
    );
  }

  if (!data || typeof data !== "object" || Array.isArray(data)) {
    return json({ ok: false, code: "invalid_gateway_response", request_id: requestId }, 502);
  }

  const result = data as Record<string, unknown>;
  const denied = result.ok === false;
  const status = denied
    ? (result.code === "authenticated_user_required" ? 401 : 403)
    : 200;

  return json(
    {
      ok: result.ok === true,
      code: typeof result.code === "string" ? result.code : undefined,
      reason: typeof result.reason === "string" ? result.reason : undefined,
      request_id: typeof result.request_id === "string" ? result.request_id : requestId,
      result: result.result ?? null,
    },
    status,
  );
});
