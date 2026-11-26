// Suma el IVA de los comprobantes devueltos por Mis Comprobantes (objetos con claves en texto).
const norm = (s) => String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/\s+/g, " ").trim();
const num = (v) => {
  if (typeof v === "number") return v;
  let s = String(v ?? "").trim().replace(/\s|\$/g, "");
  if (!s) return 0;
  if (s.includes(",") || /^-?\d{1,3}(\.\d{3})+$/.test(s)) s = s.replace(/\./g, "").replace(",", ".");
  const n = parseFloat(s);
  return isNaN(n) ? 0 : n;
};
const NC = [3, 8, 13, 53, 203, 208, 213];

export function sumar(rows) {
  let iva = 0, neto = 0, n = 0;
  const porContraparte = {};
  for (const r of rows || []) {
    const k = {};
    for (const key of Object.keys(r)) k[norm(key)] = r[key];
    const tipo = String(k["tipo de comprobante"] ?? k["tipo"] ?? "");
    const sign = NC.includes(parseInt(tipo, 10)) || /nota de cr/i.test(tipo) ? -1 : 1;
    let tc = num(k["tipo cambio"] ?? k["tipo de cambio"] ?? 1);
    if (!(tc > 0)) tc = 1;
    const vIva = num(k["total iva"] ?? k["iva"]) * tc * sign;
    const vNeto = num(k["neto gravado total"] ?? k["imp. neto gravado"] ?? 0) * tc * sign;
    iva += vIva; neto += vNeto; n++;
    const quien = String(k["denominacion emisor"] ?? k["denominacion receptor"] ?? "").slice(0, 80);
    if (quien) porContraparte[quien] = (porContraparte[quien] || 0) + vIva;
  }
  const top = Object.entries(porContraparte).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 5).map(([nombre, iva]) => ({ nombre, iva: Math.round(iva) }));
  return { iva: Math.round(iva), neto: Math.round(neto), n, top };
}

export function resultado(periodo, emitidos, recibidos) {
  const e = sumar(emitidos), r = sumar(recibidos);
  return { periodo, debito: e.iva, credito: r.iva, ventas_netas: e.neto, compras_netas: r.neto, n_emitidos: e.n, n_recibidos: r.n,
    determinado: e.iva - r.iva, top_clientes: e.top, top_proveedores: r.top, calculado: new Date().toISOString() };
}
