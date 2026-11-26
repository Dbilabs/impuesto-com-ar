// Utilidades compartidas de las Functions.
export const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });

export const clean = (v, n = 200) => String(v ?? "").replace(/[\u0000-\u001f]/g, " ").trim().slice(0, n);
export const digits = (v) => String(v ?? "").replace(/\D/g, "");

// Valida CUIT/CUIL con dígito verificador.
export function cuitValido(c) {
  c = digits(c);
  if (c.length !== 11) return false;
  const m = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2];
  let s = 0;
  for (let i = 0; i < 10; i++) s += +c[i] * m[i];
  let v = 11 - (s % 11);
  if (v === 11) v = 0;
  if (v === 10) v = 9;
  return v === +c[10];
}

const b64u = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
export const randomToken = () => b64u(crypto.getRandomValues(new Uint8Array(32)));
export async function sha256(s) {
  return b64u(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s)));
}
export const ipHash = (request) => sha256("ip:" + (request.headers.get("CF-Connecting-IP") || "0"));

// Envía una fila a Google Sheets (sin credenciales).
export async function toSheets(env, lead) {
  if (!env.SHEETS_WEBHOOK_URL) return false;
  const safe = (v) => (typeof v === "string" && /^[=+\-@]/.test(v) ? "'" + v : v);
  const row = {};
  for (const [k, v] of Object.entries(lead)) row[k] = safe(v);
  try {
    const r = await fetch(env.SHEETS_WEBHOOK_URL, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ secret: env.SHEETS_SECRET || "", lead: row }), redirect: "follow",
    });
    return !!(await r.json().catch(() => ({}))).ok;
  } catch { return false; }
}

// Período AAAA-MM → rango dd/mm/aaaa - dd/mm/aaaa (hasta hoy si es el mes en curso). Hora de Argentina.
export function rangoPeriodo(periodo) {
  const hoy = new Date(Date.now() - 3 * 3600e3);
  const [y, m] = periodo.split("-").map(Number);
  const ultimo = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const esActual = hoy.getUTCFullYear() === y && hoy.getUTCMonth() + 1 === m;
  const hasta = esActual ? hoy.getUTCDate() : ultimo;
  const p = (n) => String(n).padStart(2, "0");
  return `01/${p(m)}/${y} - ${p(hasta)}/${p(m)}/${y}`;
}
export function periodoActual() {
  const d = new Date(Date.now() - 3 * 3600e3);
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}
export function periodoValido(p) {
  if (!/^\d{4}-\d{2}$/.test(p)) return false;
  const [y, m] = p.split("-").map(Number);
  const cur = periodoActual().split("-").map(Number);
  const diff = (cur[0] - y) * 12 + (cur[1] - m);
  return m >= 1 && m <= 12 && diff >= 0 && diff <= 12;
}
