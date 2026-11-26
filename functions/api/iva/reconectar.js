// POST /api/iva/reconectar {token, usuario?, clave, guardar, periodo?} → actualiza el acceso y lanza una consulta.
import { json, digits, cuitValido, periodoActual, periodoValido } from "../../../server/util.js";
import { cuentaPorToken, guardarCredenciales, borrarCredenciales, iniciarConsulta } from "../../../server/servicio.js";

export async function onRequestPost({ request, env }) {
  const b = await request.json().catch(() => ({}));
  const cuenta = await cuentaPorToken(env, b.token);
  if (!cuenta) return json({ ok: false, error: "Enlace inválido o cuenta eliminada." }, 401);
  const usuario = digits(b.usuario || cuenta.cuit), clave = String(b.clave ?? "");
  if (!cuitValido(usuario) || !clave || clave.length > 64) return json({ ok: false, error: "Revisá el usuario y la clave fiscal." }, 400);
  const periodo = b.periodo || periodoActual();
  if (!periodoValido(periodo)) return json({ ok: false, error: "Período inválido." }, 400);
  const guardar = b.guardar === true || b.guardar === "si";
  if (guardar) await guardarCredenciales(env, cuenta.id, usuario, clave);
  else await borrarCredenciales(env, cuenta.id);
  await env.DB.prepare("UPDATE cuentas SET guardar = ? WHERE id = ?").bind(guardar ? 1 : 0, cuenta.id).run();
  try {
    const id = await iniciarConsulta(env, { ...cuenta, cred_ct: null }, periodo, { usuario, clave });
    return json({ ok: true, consulta: id });
  } catch {
    return json({ ok: false, error: "No pudimos conectar con ARCA. Revisá la clave y probá de nuevo." }, 502);
  }
}
