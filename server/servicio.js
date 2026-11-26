// Lógica del servicio "IVA automático" (cuentas, consultas). Base de datos: D1 (binding DB).
import { seal, open } from "./crypto.js";
import { bot } from "./bot.js";
import { resultado } from "./iva.js";
import { sha256, rangoPeriodo } from "./util.js";

export const ESPERA_MIN = 5; // minutos mínimos entre consultas de una misma cuenta

export async function cuentaPorToken(env, token) {
  if (!token || token.length < 20) return null;
  return env.DB.prepare("SELECT * FROM cuentas WHERE token_hash = ?").bind(await sha256("tk:" + token)).first();
}

export async function guardarCredenciales(env, cuentaId, usuario, clave) {
  const { ct, iv } = await seal(env, cuentaId, { usuario, clave });
  await env.DB.prepare("UPDATE cuentas SET cred_ct = ?, cred_iv = ? WHERE id = ?").bind(ct, iv, cuentaId).run();
}

export async function borrarCredenciales(env, cuentaId) {
  await env.DB.prepare("UPDATE cuentas SET cred_ct = NULL, cred_iv = NULL WHERE id = ?").bind(cuentaId).run();
}

// Inicia la consulta: lanza los dos trabajos del robot (emitidos y recibidos) y registra la consulta.
// Si se pasan credenciales en memoria (cuenta que no guarda acceso), se usan y se descartan.
export async function iniciarConsulta(env, cuenta, periodo, credsEnMemoria) {
  let creds = credsEnMemoria;
  if (!creds) {
    if (!cuenta.cred_ct) throw Object.assign(new Error("Tu acceso no está guardado. Volvé a conectar tu CUIT."), { code: "sin_credenciales" });
    creds = await open(env, cuenta.id, cuenta.cred_ct, cuenta.cred_iv);
  }
  const b = bot(env), rango = rangoPeriodo(periodo);
  const args = { cuit: cuenta.cuit, usuario: creds.usuario, clave: creds.clave, rango };
  const [jobE, jobR] = await Promise.all([b.start(env, { ...args, tipo: "E" }), b.start(env, { ...args, tipo: "R" })]);
  creds = null;
  const id = crypto.randomUUID();
  await env.DB.batch([
    env.DB.prepare("INSERT INTO consultas (id, cuenta_id, periodo, estado, job_e, job_r, creada) VALUES (?, ?, ?, 'en_proceso', ?, ?, ?)")
      .bind(id, cuenta.id, periodo, jobE, jobR, new Date().toISOString()),
    env.DB.prepare("UPDATE cuentas SET ultima_consulta = ? WHERE id = ?").bind(new Date().toISOString(), cuenta.id),
  ]);
  return id;
}

// Revisa el estado de los trabajos y, si terminaron, calcula y guarda el resultado.
export async function avanzarConsulta(env, consulta) {
  if (consulta.estado !== "en_proceso") return consulta;
  const b = bot(env);
  const [e, r] = await Promise.all([b.status(env, consulta.job_e), b.status(env, consulta.job_r)]);
  if (e.status === "error" || r.status === "error") {
    const msg = traducirError(e.message || r.message);
    await env.DB.prepare("UPDATE consultas SET estado = 'error', error = ? WHERE id = ?").bind(msg, consulta.id).run();
    return { ...consulta, estado: "error", error: msg };
  }
  if (e.status === "complete" && r.status === "complete") {
    const res = resultado(consulta.periodo, e.data, r.data);
    await env.DB.prepare("UPDATE consultas SET estado = 'lista', resultado = ? WHERE id = ?").bind(JSON.stringify(res), consulta.id).run();
    return { ...consulta, estado: "lista", resultado: JSON.stringify(res) };
  }
  const minutos = (Date.now() - Date.parse(consulta.creada)) / 60000;
  if (minutos > 10) {
    await env.DB.prepare("UPDATE consultas SET estado = 'error', error = ? WHERE id = ?").bind("ARCA no respondió a tiempo. Probá de nuevo más tarde.", consulta.id).run();
    return { ...consulta, estado: "error", error: "ARCA no respondió a tiempo. Probá de nuevo más tarde." };
  }
  return consulta;
}

function traducirError(m = "") {
  if (/clave|contrase|usuario|incorrect/i.test(m)) return "ARCA rechazó el usuario o la clave fiscal. Revisalos y volvé a conectar.";
  if (/cuit|cuil/i.test(m)) return "El CUIT no es válido o no está habilitado para Mis Comprobantes.";
  return "No pudimos consultar ARCA en este momento. Probá de nuevo en unos minutos.";
}

export function vistaConsulta(c) {
  return { id: c.id, periodo: c.periodo, estado: c.estado, error: c.error || null, resultado: c.resultado ? JSON.parse(c.resultado) : null };
}
