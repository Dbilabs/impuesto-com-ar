// POST /api/iva/estado {token, consulta?} → estado de una consulta (o la última) y datos de la cuenta.
import { json } from "../../../server/util.js";
import { cuentaPorToken, avanzarConsulta, vistaConsulta } from "../../../server/servicio.js";

export async function onRequestPost({ request, env }) {
  const b = await request.json().catch(() => ({}));
  const cuenta = await cuentaPorToken(env, b.token);
  if (!cuenta) return json({ ok: false, error: "Enlace inválido o cuenta eliminada." }, 401);
  let c = b.consulta
    ? await env.DB.prepare("SELECT * FROM consultas WHERE id = ? AND cuenta_id = ?").bind(b.consulta, cuenta.id).first()
    : await env.DB.prepare("SELECT * FROM consultas WHERE cuenta_id = ? ORDER BY creada DESC LIMIT 1").bind(cuenta.id).first();
  if (c) c = await avanzarConsulta(env, c);
  const historial = await env.DB.prepare("SELECT periodo, resultado FROM consultas WHERE cuenta_id = ? AND estado = 'lista' ORDER BY creada DESC LIMIT 12").bind(cuenta.id).all();
  return json({
    ok: true,
    cuenta: { cuit: cuenta.cuit, nombre: cuenta.nombre, guardar: !!cuenta.cred_ct, ultima_consulta: cuenta.ultima_consulta },
    consulta: c ? vistaConsulta(c) : null,
    historial: (historial.results || []).map((h) => ({ periodo: h.periodo, ...JSON.parse(h.resultado) })),
  });
}
