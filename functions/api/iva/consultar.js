// POST /api/iva/consultar {token, periodo?} → lanza una nueva consulta con el acceso guardado.
import { json, periodoActual, periodoValido } from "../../../server/util.js";
import { cuentaPorToken, iniciarConsulta, ESPERA_MIN } from "../../../server/servicio.js";

export async function onRequestPost({ request, env }) {
  const b = await request.json().catch(() => ({}));
  const cuenta = await cuentaPorToken(env, b.token);
  if (!cuenta) return json({ ok: false, error: "Enlace inválido o cuenta eliminada." }, 401);
  const periodo = b.periodo || periodoActual();
  if (!periodoValido(periodo)) return json({ ok: false, error: "Período inválido (hasta 12 meses atrás)." }, 400);
  if (cuenta.ultima_consulta && Date.now() - Date.parse(cuenta.ultima_consulta) < ESPERA_MIN * 60000)
    return json({ ok: false, error: `Esperá ${ESPERA_MIN} minutos entre consultas.` }, 429);
  try {
    const id = await iniciarConsulta(env, cuenta, periodo);
    return json({ ok: true, consulta: id });
  } catch (e) {
    if (e.code === "sin_credenciales") return json({ ok: false, error: e.message, reconectar: true }, 409);
    return json({ ok: false, error: "No pudimos conectar con ARCA. Probá de nuevo en unos minutos." }, 502);
  }
}
