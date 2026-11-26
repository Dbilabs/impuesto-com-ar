// POST /api/iva/desconectar {token} → borra el acceso guardado, las consultas y la cuenta.
import { json } from "../../../server/util.js";
import { cuentaPorToken } from "../../../server/servicio.js";

export async function onRequestPost({ request, env }) {
  const b = await request.json().catch(() => ({}));
  const cuenta = await cuentaPorToken(env, b.token);
  if (!cuenta) return json({ ok: true });
  await env.DB.batch([
    env.DB.prepare("DELETE FROM consultas WHERE cuenta_id = ?").bind(cuenta.id),
    env.DB.prepare("DELETE FROM cuentas WHERE id = ?").bind(cuenta.id),
  ]);
  return json({ ok: true });
}
