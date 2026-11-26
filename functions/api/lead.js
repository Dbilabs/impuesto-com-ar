// Cloudflare Pages Function: POST /api/lead
// Valida el lead, calcula puntaje y destino (Auren / Calim) y lo envía a Google Sheets (Apps Script).
// Variables de entorno (Cloudflare Pages → Settings → Environment variables):
//   SHEETS_WEBHOOK_URL  URL de la implementación web de Apps Script
//   SHEETS_SECRET       el mismo secreto configurado en Apps Script

const MAX = 1200;
const clean = (v, n = 200) => String(v ?? "").replace(/[\u0000-\u001f]/g, " ").trim().slice(0, n);
// Evita inyección de fórmulas al abrir en Sheets/Excel
const safe = (v) => (/^[=+\-@]/.test(v) ? "'" + v : v);

const TEMAS_AUREN = new Set(["auditoria", "precios-transferencia", "fiscalizacion", "planificacion", "convenio-multilateral", "saldos-a-favor", "cambiar-estudio"]);
const FACT_ALTA = ["Entre $3.000 y $15.000 millones", "Más de $15.000 millones"];
const FACT_MEDIA = ["Entre $500 y $3.000 millones"];
const EMP_GRANDES = ["11 a 50 empleados", "51 a 200 empleados", "Más de 200 empleados"];

function rutear(l) {
  // Devuelve { destino, puntaje, motivo }
  if (l.perfil === "empresa") {
    let pts = 40;
    if (FACT_ALTA.includes(l.facturacion)) pts += 40;
    else if (FACT_MEDIA.includes(l.facturacion)) pts += 25;
    if (EMP_GRANDES.includes(l.situacion)) pts += 15;
    if (["auditoria", "precios-transferencia"].includes(l.tema)) pts += 10;
    const grande = FACT_ALTA.includes(l.facturacion) || FACT_MEDIA.includes(l.facturacion) || EMP_GRANDES.includes(l.situacion);
    if (grande || ["auditoria", "precios-transferencia"].includes(l.tema)) {
      return { destino: "Auren", puntaje: Math.min(pts, 100), motivo: "Empresa mediana o tema de auditoría/impuestos complejos" };
    }
    return { destino: TEMAS_AUREN.has(l.tema) ? "Auren (revisar)" : "Calim", puntaje: Math.min(pts, 100), motivo: "Empresa chica" };
  }
  if (l.perfil === "ri") {
    let pts = 35;
    if (l.situacion === "Más de $500 millones por año") return { destino: "Auren", puntaje: 75, motivo: "Responsable inscripto de facturación alta" };
    if (l.situacion === "Entre $100 y $500 millones por año") pts += 20;
    if (["iva-planificacion", "saldos-a-favor", "iva-automatico"].includes(l.tema)) pts += 10;
    return { destino: "Calim", puntaje: pts, motivo: "Responsable inscripto / profesional" };
  }
  let pts = 20;
  if (l.tema === "exclusion") pts += 20;
  if (l.situacion === "Soy responsable inscripto / autónomo") pts += 15;
  return { destino: "Calim", puntaje: pts, motivo: "Persona / monotributo" };
}

const json = (obj, status = 200) => new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });

export async function onRequestPost({ request, env }) {
  let body;
  try { body = await request.json(); } catch { return json({ ok: false, error: "json" }, 400); }
  if (body.web) return json({ ok: true }); // honeypot: bots

  const l = {
    perfil: clean(body.perfil, 20), tema: clean(body.tema, 40), situacion: clean(body.situacion, 80),
    nombre: clean(body.nombre, 120), email: clean(body.email, 160).toLowerCase(), whatsapp: clean(body.whatsapp, 40),
    empresa: clean(body.empresa, 160), cargo: clean(body.cargo, 120), facturacion: clean(body.facturacion, 60),
    provincia: clean(body.provincia, 60), mensaje: clean(body.mensaje, MAX), consentimiento: body.consentimiento === "si" ? "si" : "",
    pagina: clean(body.pagina, 200), landing: clean(body.landing, 200), referrer: clean(body.referrer, 300),
    utm_source: clean(body.utm_source, 100), utm_medium: clean(body.utm_medium, 100), utm_campaign: clean(body.utm_campaign, 150),
    utm_term: clean(body.utm_term, 150), utm_content: clean(body.utm_content, 150), gclid: clean(body.gclid, 200),
  };
  if (!["persona", "empresa", "ri"].includes(l.perfil)) return json({ ok: false, error: "perfil" }, 400);
  if (!l.nombre || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(l.email) || l.whatsapp.replace(/\D/g, "").length < 8) return json({ ok: false, error: "datos" }, 400);
  if (l.consentimiento !== "si") return json({ ok: false, error: "consentimiento" }, 400);

  const r = rutear(l);
  const row = {
    fecha: new Date().toISOString(), ...l, destino: r.destino, puntaje: r.puntaje, motivo_ruteo: r.motivo,
    pais_ip: request.cf?.country || "", estado: "Nuevo",
  };
  for (const k of Object.keys(row)) if (typeof row[k] === "string") row[k] = safe(row[k]);

  if (!env.SHEETS_WEBHOOK_URL) return json({ ok: false, error: "config" }, 500);
  try {
    const res = await fetch(env.SHEETS_WEBHOOK_URL, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ secret: env.SHEETS_SECRET || "", lead: row }), redirect: "follow",
    });
    const out = await res.json().catch(() => ({}));
    if (!out.ok) return json({ ok: false, error: "sheets" }, 502);
  } catch (e) {
    return json({ ok: false, error: "sheets" }, 502);
  }
  return json({ ok: true });
}

export const onRequest = () => json({ ok: false, error: "method" }, 405);
