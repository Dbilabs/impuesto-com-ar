// Robot que consulta "Mis Comprobantes" en ARCA.
// Proveedores (variable BOT_PROVIDER):
//   propio   → Microservicio propio de Playwright (BOT_API_URL). Recomendado y sin costos por consulta.
//   afipsdk  → API de automatizaciones de Afip SDK (https://afipsdk.com). Requiere AFIPSDK_TOKEN.
//   mock     → datos de ejemplo, para desarrollo y pruebas.

const AFIPSDK = "https://app.afipsdk.com/api/v1/automations";

const providers = {
  propio: {
    async start(env, { cuit, usuario, clave, tipo, rango }) {
      const url = env.BOT_API_URL || "http://localhost:8000/api/v1/automations";
      const headers = { "Content-Type": "application/json" };
      if (env.BOT_API_TOKEN) headers["Authorization"] = `Bearer ${env.BOT_API_TOKEN}`;
      const r = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify({ automation: "mis-comprobantes", params: { cuit, username: usuario, password: clave, filters: { t: tipo, fechaEmision: rango } } }),
      });
      const j = await r.json().catch(() => ({}));
      if (!j.id) throw new Error(j?.data?.message || j?.detail || j?.message || "No se pudo iniciar la consulta en ARCA");
      return j.id;
    },
    async status(env, id) {
      const url = env.BOT_API_URL || "http://localhost:8000/api/v1/automations";
      const headers = {};
      if (env.BOT_API_TOKEN) headers["Authorization"] = `Bearer ${env.BOT_API_TOKEN}`;
      const r = await fetch(`${url}/${id}`, { headers });
      const j = await r.json().catch(() => ({}));
      if (j.status === "complete") return { status: "complete", data: j.data || [] };
      if (j.status === "error") return { status: "error", message: j?.data?.message || j?.message || "Error en ARCA" };
      return { status: "in_process" };
    },
  },
  afipsdk: {
    // tipo: "E" emitidos | "R" recibidos. Devuelve el id del trabajo.
    async start(env, { cuit, usuario, clave, tipo, rango }) {
      const r = await fetch(AFIPSDK, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.AFIPSDK_TOKEN}` },
        body: JSON.stringify({ automation: "mis-comprobantes", params: { cuit, username: usuario, password: clave, filters: { t: tipo, fechaEmision: rango } } }),
      });
      const j = await r.json().catch(() => ({}));
      if (!j.id) throw new Error(j?.data?.message || "No se pudo iniciar la consulta en ARCA");
      return j.id;
    },
    // Devuelve { status: "in_process" | "complete" | "error", data?, message? }
    async status(env, id) {
      const r = await fetch(`${AFIPSDK}/${id}`, { headers: { Authorization: `Bearer ${env.AFIPSDK_TOKEN}` } });
      const j = await r.json().catch(() => ({}));
      if (j.status === "complete") return { status: "complete", data: j.data || [] };
      if (j.status === "error") return { status: "error", message: j?.data?.message || "Error en ARCA" };
      return { status: "in_process" };
    },
  },
  mock: {
    async start(env, { tipo, clave }) {
      if (clave === "incorrecta") throw new Error("Clave o usuario incorrecto");
      return `mock-${tipo}-${crypto.randomUUID()}`;
    },
    async status(env, id) {
      const E = id.startsWith("mock-E");
      const row = (tipo, neto, iva, tc = "1,00") => ({ "Fecha de Emisión": "03/11/2026", "Tipo de Comprobante": tipo, "Tipo Cambio": tc, "Imp. Neto Gravado": neto, IVA: iva, "Denominación Receptor": E ? "Cliente SA" : "Proveedor SRL" });
      return {
        status: "complete",
        data: E
          ? [row("1 - Factura A", "10000000,00", "2100000,00"), row("6 - Factura B", "2000000,00", "420000,00"), row("3 - Nota de Crédito A", "1000000,00", "210000,00")]
          : [row("1 - Factura A", "6000000,00", "1260000,00"), row("1 - Factura A", "1000,00", "210,00", "1000,00")],
      };
    },
  },
};

export function bot(env) {
  const provider = env.BOT_PROVIDER || (env.BOT_API_URL ? "propio" : "afipsdk");
  const p = providers[provider];
  if (!p) throw new Error("BOT_PROVIDER inválido");
  if (provider === "afipsdk" && !env.AFIPSDK_TOKEN) throw new Error("Falta AFIPSDK_TOKEN");
  return p;
}
