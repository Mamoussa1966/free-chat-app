const SERVICE_NAME = "ai-council-cloudflare-canary";
const RELEASE_ID = "canary-2026-11-09.1";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
    },
  });
}

export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname !== "/health") {
      return new Response("Not Found", {
        status: 404,
        headers: {
          "cache-control": "no-store",
          "x-content-type-options": "nosniff",
        },
      });
    }

    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method Not Allowed", {
        status: 405,
        headers: {
          allow: "GET, HEAD",
          "cache-control": "no-store",
        },
      });
    }

    const body = {
      ok: true,
      service: SERVICE_NAME,
      release: RELEASE_ID,
    };

    if (request.method === "HEAD") {
      return new Response(null, {
        status: 200,
        headers: {
          "content-type": "application/json; charset=utf-8",
          "cache-control": "no-store",
          "x-content-type-options": "nosniff",
        },
      });
    }

    return jsonResponse(body);
  },
} satisfies ExportedHandler;
