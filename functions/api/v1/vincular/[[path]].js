// Cloudflare Pages Function: https://impuesto.com.ar/api/v1/vincular/*
// Proxy cifrado hacia la bóveda del backend headless (BOT_API_URL).

export async function onRequest({ request, env, params }) {
  if (!env.BOT_API_URL) {
    return new Response(JSON.stringify({ ok: false, error: "Backend de bóveda no configurado." }), {
      status: 503,
      headers: { "Content-Type": "application/json; charset=utf-8" }
    });
  }
  const tail = (params.path || []).join("/");
  const target = `${env.BOT_API_URL.replace(/\/$/, "")}/api/v1/vincular${tail ? "/" + tail : ""}`;
  const headers = new Headers();
  if (request.headers.get("Content-Type")) headers.set("Content-Type", request.headers.get("Content-Type"));
  if (request.headers.get("Authorization")) headers.set("Authorization", request.headers.get("Authorization"));
  if (request.headers.get("X-User-Token")) headers.set("X-User-Token", request.headers.get("X-User-Token"));
  if (env.BOT_API_SECRET) headers.set("X-Bot-Secret", env.BOT_API_SECRET);

  const resp = await fetch(target, {
    method: request.method,
    headers,
    body: request.method !== "GET" && request.method !== "HEAD" ? request.body : undefined
  });
  return new Response(resp.body, {
    status: resp.status,
    headers: {
      "Content-Type": resp.headers.get("Content-Type") || "application/json; charset=utf-8",
      "Cache-Control": "no-store"
    }
  });
}
