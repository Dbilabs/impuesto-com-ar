// Cloudflare Pages Function: https://impuesto.com.ar/vincular
// Proxy transparente hacia la bóveda cifrada del backend headless (BOT_API_URL)
// para que el usuario SIEMPRE vincule su CUIT bajo el dominio oficial impuesto.com.ar.

export async function onRequest({ request, env }) {
  if (!env.BOT_API_URL) {
    return new Response("Servicio de vinculación en mantenimiento. Reintentá en unos minutos.", {
      status: 503,
      headers: { "Content-Type": "text/plain; charset=utf-8" }
    });
  }
  const url = new URL(request.url);
  const target = `${env.BOT_API_URL.replace(/\/$/, "")}/vincular${url.search || ""}`;
  const resp = await fetch(target, {
    method: request.method,
    headers: { "Accept": request.headers.get("Accept") || "text/html" }
  });
  return new Response(resp.body, {
    status: resp.status,
    headers: {
      "Content-Type": resp.headers.get("Content-Type") || "text/html; charset=utf-8",
      "Cache-Control": "no-store"
    }
  });
}
