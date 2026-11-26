// Cloudflare Pages Middleware: enrutamiento dedicado para subdominios MCP
// Permite conectar directamente con:
//   • https://claude.impuesto.com.ar
//   • https://chatgpt.impuesto.com.ar
//   • https://gemini.impuesto.com.ar
//   • https://copilot.impuesto.com.ar
//   • https://cursor.impuesto.com.ar
//   • https://perplexity.impuesto.com.ar
//   • https://mcp.impuesto.com.ar
// sin necesidad de recordar rutas internas (/mcp/sse).

import { onRequest as handleMcp } from "./mcp/[[path]].js";

const MCP_HOSTS = new Set([
  "claude.impuesto.com.ar",
  "chatgpt.impuesto.com.ar",
  "gemini.impuesto.com.ar",
  "copilot.impuesto.com.ar",
  "cursor.impuesto.com.ar",
  "perplexity.impuesto.com.ar",
  "mcp.impuesto.com.ar",
  "api.impuesto.com.ar"
]);

export async function onRequest(context) {
  const url = new URL(context.request.url);
  const host = url.hostname.toLowerCase();

  if (MCP_HOSTS.has(host)) {
    // Normalizar subruta: "/" -> [], "/sse" -> ["sse"], "/messages" -> ["messages"], "/mcp/sse" -> ["sse"]
    const clean = url.pathname.replace(/^\/+/, "").replace(/^mcp\/?/, "");
    const parts = clean ? clean.split("/") : [];
    return handleMcp({
      request: context.request,
      env: context.env,
      params: { path: parts }
    });
  }

  return context.next();
}
