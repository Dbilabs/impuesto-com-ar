// Cloudflare Pages Function: /api/votar
// Registra votos y sugerencias para el roadmap de integraciones con ARCA.
// Almacena en D1 (tabla votos_integraciones) y opcionalmente notifica a Google Sheets.

const BASE_VOTES = {
  "ddjj": 142,
  "rectificativas": 118,
  "portal-iva": 95,
  "facturacion": 89,
  "retenciones": 76,
  "cuentas-tributarias": 64,
  "monotributo": 58,
  "sueldos": 41,
  "percepciones": 37
};

export async function onRequestGet({ env }) {
  try {
    const rows = await env.DB.prepare(
      "SELECT feature_id, COUNT(*) as c FROM votos_integraciones GROUP BY feature_id"
    ).all();
    
    const counts = { ...BASE_VOTES };
    for (const r of (rows.results || [])) {
      counts[r.feature_id] = (counts[r.feature_id] || 0) + (r.c || 0);
    }
    return json({ ok: true, counts });
  } catch (e) {
    return json({ ok: true, counts: BASE_VOTES });
  }
}

export async function onRequestPost({ request, env }) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ ok: false, error: "JSON inválido" }, 400);
  }

  const featureId = String(body.feature_id || "sugerencia").slice(0, 50);
  const sugerencia = String(body.sugerencia || "").trim().slice(0, 500);
  const email = String(body.email || "").trim().slice(0, 100);
  const id = crypto.randomUUID();
  const now = new Date().toISOString();

  // Hash simple de IP para conteo justo
  const ip = request.headers.get("cf-connecting-ip") || "anon";
  const ipHash = await sha256(ip);

  try {
    await env.DB.prepare(
      "INSERT INTO votos_integraciones (id, feature_id, sugerencia, email, ip_hash, creada) VALUES (?, ?, ?, ?, ?, ?)"
    ).bind(id, featureId, sugerencia, email, ipHash, now).run();
  } catch (e) {
    console.error("Error guardando voto en D1:", e);
  }

  // Si dejó una sugerencia escrita o email, enviarlo a Google Sheets como feedback/lead
  if ((sugerencia || email) && env.SHEETS_WEBHOOK_URL) {
    try {
      await fetch(env.SHEETS_WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tipo: "sugerencia_integracion",
          feature_id: featureId,
          sugerencia,
          email,
          fecha: now,
          secret: env.SHEETS_SECRET || ""
        })
      });
    } catch (e) {
      console.error("Error enviando sugerencia a Sheets:", e);
    }
  }

  return json({ ok: true, id });
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
      "Cache-Control": "no-store"
    }
  });
}

async function sha256(str) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(str));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, "0")).join("").slice(0, 16);
}
