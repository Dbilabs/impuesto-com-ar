// POST /api/iva/conectar  → crea la cuenta, guarda el acceso cifrado (si el cliente lo autoriza) y lanza la primera consulta.
import { json, clean, digits, cuitValido, randomToken, sha256, ipHash, toSheets, periodoActual } from "../../../server/util.js";
import { guardarCredenciales, iniciarConsulta } from "../../../server/servicio.js";

export async function onRequestPost({ request, env }) {
  let b;
  try { b = await request.json(); } catch { return json({ ok: false, error: "Solicitud inválida" }, 400); }
  if (b.web) return json({ ok: false, error: "Solicitud inválida" }, 400); // honeypot

  const cuit = digits(b.cuit), usuario = digits(b.usuario || b.cuit), clave = String(b.clave ?? "");
  const email = clean(b.email, 160).toLowerCase(), nombre = clean(b.nombre, 120), whatsapp = clean(b.whatsapp, 40);
  const guardar = b.guardar === true || b.guardar === "si";
  if (!cuitValido(cuit)) return json({ ok: false, error: "El CUIT a consultar no es válido." }, 400);
  if (!cuitValido(usuario)) return json({ ok: false, error: "El usuario de ARCA (CUIT/CUIL) no es válido." }, 400);
  if (!clave || clave.length > 64) return json({ ok: false, error: "Ingresá tu clave fiscal." }, 400);
  if (!nombre || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return json({ ok: false, error: "Completá tu nombre y un email válido." }, 400);
  if (b.autorizacion !== "si") return json({ ok: false, error: "Necesitamos tu autorización expresa para consultar ARCA en tu nombre." }, 400);

  // Límite: 5 conexiones por IP por hora.
  const ip = await ipHash(request);
  const hace1h = new Date(Date.now() - 3600e3).toISOString();
  const { n } = await env.DB.prepare("SELECT COUNT(*) AS n FROM cuentas WHERE ip_hash = ? AND creada > ?").bind(ip, hace1h).first();
  if (n >= 5) return json({ ok: false, error: "Demasiados intentos. Probá en una hora." }, 429);

  const id = crypto.randomUUID(), token = randomToken(), ahora = new Date().toISOString();
  await env.DB.prepare(
    "INSERT INTO cuentas (id, token_hash, cuit, nombre, email, whatsapp, guardar, autorizacion_texto, autorizacion_fecha, ip_hash, creada) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
  ).bind(id, await sha256("tk:" + token), cuit, nombre, email, whatsapp, guardar ? 1 : 0, clean(b.autorizacion_texto, 1500), ahora, ip, ahora).run();

  if (guardar) await guardarCredenciales(env, id, usuario, clave);
  const cuenta = await env.DB.prepare("SELECT * FROM cuentas WHERE id = ?").bind(id).first();

  let consultaId;
  try {
    consultaId = await iniciarConsulta(env, cuenta, periodoActual(), guardar ? null : { usuario, clave });
  } catch (e) {
    await env.DB.prepare("DELETE FROM cuentas WHERE id = ?").bind(id).run();
    return json({ ok: false, error: /clave|usuario|incorrect/i.test(e.message) ? "ARCA rechazó el usuario o la clave fiscal." : "No pudimos conectar con ARCA. Probá de nuevo en unos minutos." }, 502);
  }

  // Lead en la planilla (sin credenciales ni token).
  await toSheets(env, { fecha: ahora, estado: "Nuevo", destino: "Calim", puntaje: 60, motivo_ruteo: "Conectó IVA automático", perfil: "ri", tema: "iva-automatico",
    nombre, email, whatsapp, empresa: cuit, consentimiento: "si", pagina: "/iva/" });

  return json({ ok: true, token, consulta: consultaId, guardar });
}
