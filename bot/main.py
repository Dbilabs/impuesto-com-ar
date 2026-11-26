"""
bot/main.py
Microservicio Backend Headless Multi-Tenant de impuesto.com.ar (BOT_API_URL).

Expone:
  - GET  /health                    -> Estado del servicio
  - GET  /vincular                  -> Portal cifrado de vinculación única + generación de Token Multi-LLM
  - POST /api/v1/vincular           -> Guarda credenciales cifradas (AES+HMAC), asigna Owner y emite Token personal
  - GET  /api/v1/vincular/{cuit}    -> Verifica estado de vinculación (nunca expone secretos)
  - DELETE /api/v1/vincular/{cuit}  -> Revoca acceso en 1 clic
  - POST /api/v1/mcp/tool           -> Ejecutor headless con aislamiento estricto por Email/Token e Historial Cross-LLM
  - POST /api/v1/automations        -> Compatibilidad con jobs asíncronos de Mis Comprobantes
"""

import os
import uuid
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .scraper import consultar_mis_comprobantes
from .boveda_segura import (
    guardar_credenciales_cifradas,
    obtener_credenciales_descifradas,
    estado_vinculacion,
    revocar_credenciales,
    listar_cuits_autorizados,
    crear_token_usuario,
    resolver_email_por_token,
    verificar_permiso_cuit,
    autorizar_usuario_cuit,
    revocar_usuario_cuit,
    listar_accesos_cuit,
    registrar_evento_historial,
    obtener_historial_actividad,
    normalizar_cuit,
    normalizar_email,
)
from .auditoria_unificada import auditar_estado_integral_arca

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("arca_api")

app = FastAPI(title="impuesto.com.ar — ARCA Headless Multi-Tenant Engine", version="3.0.0")
executor = ThreadPoolExecutor(max_workers=4)
jobs: Dict[str, Dict[str, Any]] = {}

# Caché TTL (15 min) + deduplicación de auditorías y scrapers ARCA en curso para evitar timeouts en Gemini Online / Cloudflare
AUDIT_TTL_SEC = int(os.environ.get("AUDIT_CACHE_TTL_SEC", "900"))
AUDIT_SYNC_WAIT_SEC = float(os.environ.get("AUDIT_SYNC_WAIT_SEC", "6.0"))
_audit_lock = threading.Lock()
AUDIT_CACHE: Dict[str, Dict[str, Any]] = {}
AUDIT_INFLIGHT: Dict[str, Dict[str, Any]] = {}
TOOL_CACHE: Dict[str, Dict[str, Any]] = {}
TOOL_INFLIGHT: Dict[str, Dict[str, Any]] = {}


class AutomationFilters(BaseModel):
    t: str
    fechaEmision: str


class AutomationParams(BaseModel):
    cuit: str
    username: str
    password: str
    filters: AutomationFilters


class StartRequest(BaseModel):
    automation: str
    params: AutomationParams


class VincularRequest(BaseModel):
    cuit: Optional[str] = ""
    clave_fiscal: Optional[str] = None
    email: Optional[str] = ""
    etiqueta_token: Optional[str] = "principal"
    token_personalizado: Optional[str] = ""
    modo: str = "solo_lectura_cifrada"
    cert_pem: Optional[str] = None
    key_pem: Optional[str] = None
    alias: str = ""


class McpToolRequest(BaseModel):
    name: str
    arguments: Dict[str, Any] = {}


def _check_secret(x_bot_secret: Optional[str]):
    expected = os.environ.get("BOT_API_SECRET", "").strip()
    if expected and (x_bot_secret or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Unauthorized BOT_API_SECRET")


def _auth_required_error(public_base: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "requiere_autenticacion": True,
        "acceso_denegado": True,
        "mensaje": (
            "Por seguridad multi-usuario, para consultar tu bóveda o ARCA necesitás conectarte con tu URL privada "
            "(con tu token personal ligado a tu email). "
            f"Generala en 10 segundos en {public_base}/vincular y pegala en Gemini, Claude o ChatGPT. "
            "Así solo vos (y los emails que vos autorices) pueden ver tus CUITs y tu historial compartido."
        ),
        "url_vinculacion_segura": f"{public_base}/vincular",
    }


def _resolve_creds_authorized(
    actor_email: str,
    args: Dict[str, Any],
    public_base_url: str,
    nivel: str = "lectura",
):
    """Resuelve CUIT + Clave Fiscal verificando SIEMPRE que `actor_email` sea Owner o invitado autorizado."""
    cuit = normalizar_cuit(
        args.get("cuit")
        or args.get("cuit_empresa")
        or args.get("cuit_emisor")
        or args.get("usuario")
        or ""
    )
    if not cuit:
        autorizados = listar_cuits_autorizados(actor_email)
        if len(autorizados) == 1:
            cuit = autorizados[0]["cuit"]
        elif len(autorizados) > 1:
            return None, None, {
                "ok": False,
                "requiere_seleccion_cuit": True,
                "usuario": actor_email,
                "cuits_disponibles": [{"cuit": x["cuit"], "rol": x["rol"], "alias": x["alias"]} for x in autorizados],
                "mensaje": "Tenés más de un CUIT autorizado en tu cuenta. Indicame cuál querés consultar.",
            }
        else:
            return None, None, {
                "ok": False,
                "requiere_vinculacion": True,
                "usuario": actor_email,
                "mensaje": f"Tu cuenta ({actor_email}) todavía no tiene ningún CUIT vinculado ni autorizado. Vinculá tu CUIT en {public_base_url}/vincular o pedile al Owner que te autorice por email.",
                "url_vinculacion_segura": f"{public_base_url}/vincular",
            }

    ok_perm, role, reason = verificar_permiso_cuit(actor_email, cuit, nivel=nivel)
    if not ok_perm:
        return cuit, None, {
            "ok": False,
            "acceso_denegado": True,
            "cuit": cuit,
            "usuario": actor_email,
            "mensaje": reason,
            "url_vinculacion_segura": f"{public_base_url}/vincular?cuit={cuit}",
        }

    rec = obtener_credenciales_descifradas(cuit)
    if rec and rec.get("clave_fiscal"):
        return cuit, rec["clave_fiscal"], None

    return cuit, None, {
        "ok": False,
        "requiere_vinculacion": True,
        "cuit": cuit,
        "mensaje": f"El CUIT {cuit} no tiene credenciales activas en la bóveda. Vinculalo en {public_base_url}/vincular?cuit={cuit}.",
        "url_vinculacion_segura": f"{public_base_url}/vincular?cuit={cuit}",
    }


def _run_auditoria_background(cuit: str, clave: str, entry: Dict[str, Any], actor_email: str = "", origen_llm: str = "mcp") -> None:
    try:
        res = auditar_estado_integral_arca(cuit=cuit, clave=clave)
        now = time.time()
        with _audit_lock:
            entry["result"] = res
            entry["finished_at"] = now
            if isinstance(res, dict) and res.get("ok") is not False:
                AUDIT_CACHE[cuit] = {"ts": now, "data": res}
            AUDIT_INFLIGHT.pop(cuit, None)
        if actor_email:
            ccma_deuda = ((res or {}).get("ccma") or {}).get("saldo_deudor_vencido", 0)
            planes = ((res or {}).get("mis_facilidades") or {}).get("cantidad_planes_vigentes", 0)
            registrar_evento_historial(
                email=actor_email,
                cuit=cuit,
                origen_llm=origen_llm,
                accion="auditoria_360_completada",
                titulo=f"Auditoría 360° ARCA completada (CUIT {cuit})",
                detalle=f"CCMA vencido: ${ccma_deuda} · Planes vigentes Mis Facilidades: {planes}",
            )
    except Exception as e:
        logger.exception(f"Error en auditoria_unificada background para {cuit}")
        with _audit_lock:
            entry["result"] = {"ok": False, "cuit": cuit, "error": str(e)}
            entry["finished_at"] = time.time()
            AUDIT_INFLIGHT.pop(cuit, None)
    finally:
        entry["event"].set()


def _ejecutar_auditoria_sin_timeout(
    cuit: str,
    clave: str,
    forzar_refresco: bool = False,
    actor_email: str = "",
    origen_llm: str = "mcp",
) -> Dict[str, Any]:
    """Ejecuta la auditoría 360° con caché de 15 min y espera máx. de 6s para evitar timeouts en Gemini Online / Cloudflare."""
    now = time.time()
    with _audit_lock:
        cached = AUDIT_CACHE.get(cuit)
        if not forzar_refresco and cached and (now - cached["ts"]) < AUDIT_TTL_SEC:
            out = dict(cached["data"])
            out["desde_cache"] = True
            out["antiguedad_seg"] = int(now - cached["ts"])
            return out

        inflight = AUDIT_INFLIGHT.get(cuit)
        if inflight is None:
            inflight = {
                "started_at": now,
                "event": threading.Event(),
                "result": None,
            }
            AUDIT_INFLIGHT[cuit] = inflight
            executor.submit(_run_auditoria_background, cuit, clave, inflight, actor_email, origen_llm)

    finished = inflight["event"].wait(timeout=AUDIT_SYNC_WAIT_SEC)
    if finished and inflight.get("result") is not None:
        return inflight["result"]

    elapsed = int(time.time() - inflight["started_at"])
    return {
        "ok": True,
        "estado": "EN_PROGRESO",
        "cuit": cuit,
        "tiempo_transcurrido_seg": elapsed,
        "mensaje": (
            f"Auditoría integral de ARCA en curso para CUIT {cuit} (lleva {elapsed}s). "
            "Estamos relevando CCMA, Mis Facilidades (Ver Pagos), SCT y Portal Monotributo en segundo plano. "
            "Suele demorar entre 1 y 3 minutos dependiendo de la velocidad de ARCA."
        ),
        "instruccion_para_ia": (
            "Respondé al usuario de forma breve y clara: avisale que ya estamos relevando en segundo plano "
            "sus 4 módulos oficiales en ARCA (CCMA, Mis Facilidades, SCT y Monotributo), que es normal que "
            "demore entre 1 y 3 minutos, que no cierre la sesión y que en 1 minuto te escriba '¿ya terminó?' "
            "para mostrarle el informe completo al instante (en la próxima llamada a `auditar_estado_integral_arca` "
            "devolverá el informe completo desde caché en menos de 1 segundo)."
        ),
    }


def _run_tool_sin_timeout(
    cache_key: str,
    label: str,
    fn,
    cuit: str,
    actor_email: str = "",
    origen_llm: str = "mcp",
    accion_hist: str = "",
) -> Dict[str, Any]:
    """Ejecuta cualquier scraper ARCA en segundo plano con caché de 15 min y espera máx. 6s para evitar cuelgues en Gemini Online."""
    now = time.time()
    with _audit_lock:
        cached = TOOL_CACHE.get(cache_key)
        if cached and (now - cached["ts"]) < AUDIT_TTL_SEC:
            data = cached["data"]
            if isinstance(data, dict):
                out = dict(data)
                out["desde_cache"] = True
                return out
            return {"ok": True, "desde_cache": True, "resultado": data}

        inflight = TOOL_INFLIGHT.get(cache_key)
        if inflight is None:
            inflight = {"started_at": now, "event": threading.Event(), "result": None}
            TOOL_INFLIGHT[cache_key] = inflight

            def _worker():
                try:
                    res = fn()
                    ts_done = time.time()
                    with _audit_lock:
                        inflight["result"] = res
                        TOOL_CACHE[cache_key] = {"ts": ts_done, "data": res}
                        TOOL_INFLIGHT.pop(cache_key, None)
                    if actor_email and accion_hist:
                        registrar_evento_historial(actor_email, cuit, origen_llm, accion_hist, f"{label} (CUIT {cuit})")
                except Exception as e:
                    logger.exception(f"Error en {cache_key}")
                    with _audit_lock:
                        inflight["result"] = {"ok": False, "cuit": cuit, "error": str(e)}
                        TOOL_INFLIGHT.pop(cache_key, None)
                finally:
                    inflight["event"].set()

            executor.submit(_worker)

    if inflight["event"].wait(timeout=AUDIT_SYNC_WAIT_SEC) and inflight.get("result") is not None:
        return inflight["result"]

    elapsed = int(time.time() - inflight["started_at"])
    return {
        "ok": True,
        "estado": "EN_PROGRESO",
        "cuit": cuit,
        "modulo": label,
        "tiempo_transcurrido_seg": elapsed,
        "mensaje": f"{label} en curso en ARCA en segundo plano para CUIT {cuit} (lleva {elapsed}s). Volvé a consultar en ~1 minuto y se entrega al instante desde caché.",
        "instruccion_para_ia": f"Avisale al usuario en 1 línea que {label} sigue procesándose en segundo plano en ARCA y que en ~1 minuto vuelva a preguntar para verlo al instante sin que se cuelgue la sesión.",
    }


@app.get("/health")
def health():
    with _audit_lock:
        c_count = len(AUDIT_CACHE)
        i_count = len(AUDIT_INFLIGHT)
    return {
        "status": "ok",
        "version": "3.0.0",
        "mode": "headless_vault_multitenant",
        "active_jobs": len(jobs),
        "cached_audits": c_count,
        "inflight_audits": i_count,
    }


@app.get("/vincular", response_class=HTMLResponse)
def vincular_page(cuit: str = "", tipo: str = ""):
    cuit_val = normalizar_cuit(cuit)
    is_estudio = tipo.lower() == "estudio"
    sel_estudio = "selected" if is_estudio else ""
    return f"""<!doctype html>
<html lang="es-AR">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vinculación Segura Multi-LLM — impuesto.com.ar</title>
<style>
:root{{--ink:#0B1320;--muted:#475467;--line:#E3E7EC;--bg:#F8FAFC;--acc:#0B6E4F;--acc2:#074F39;--tint:#E7F5EF;--font:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
*{{box-sizing:border-box}} body{{margin:0;font-family:var(--font);color:var(--ink);background:var(--bg);padding:36px 18px;line-height:1.55}}
.card{{max-width:620px;margin:0 auto;background:#fff;border:1px solid var(--line);border-radius:18px;padding:34px;box-shadow:0 14px 36px rgba(15,27,45,.07)}}
.badge{{background:var(--tint);color:var(--acc2);font-weight:700;font-size:12px;padding:4px 12px;border-radius:99px;display:inline-block;margin-bottom:12px}}
h1{{margin:0 0 8px;font-size:24px;letter-spacing:-.02em}} p{{color:var(--muted);font-size:14.5px;margin:0 0 18px}}
label{{display:block;font-weight:600;font-size:13.5px;margin:12px 0 6px}}
input,select{{width:100%;padding:11px 13px;border:1px solid #CBD5E1;border-radius:10px;font-size:14.5px}}
.btn{{margin-top:20px;width:100%;background:var(--acc);color:#fff;border:0;padding:13px;border-radius:10px;font-weight:700;font-size:15px;cursor:pointer}}
.btn:hover{{background:var(--acc2)}}
.sec{{margin-top:18px;background:#F8FAFC;border:1px solid var(--line);border-radius:12px;padding:14px;font-size:13px;color:var(--muted)}}
.sec strong{{color:var(--ink)}} #msg{{margin-top:14px;font-weight:600;font-size:14px}}
.urls{{margin-top:16px;display:none;background:#F0FDF4;border:1px solid #BBF7D0;border-radius:12px;padding:16px}}
.url-row{{display:flex;align-items:center;justify-content:space-between;gap:10px;background:#fff;border:1px solid #D1FAE5;border-radius:8px;padding:8px 10px;margin-top:8px;font-size:12.5px;font-family:ui-monospace,monospace}}
.copy{{background:var(--acc);color:#fff;border:0;border-radius:6px;padding:6px 10px;font-size:12px;font-weight:600;cursor:pointer;white-space:nowrap}}
.pw-wrap{{position:relative;display:flex;align-items:center}}
.pw-wrap input{{padding-right:78px}}
.pw-toggle{{position:absolute;right:8px;background:#F1F5F9;border:1px solid #CBD5E1;color:var(--ink);border-radius:7px;padding:5px 9px;font-size:12px;font-weight:600;cursor:pointer}}
.pw-toggle:hover{{background:#E2E8F0}}
.hint{{font-size:12.5px;margin-top:5px;font-weight:600}}
</style>
</head>
<body>
<div class="card">
  <span class="badge">🔒 Bóveda Multi-Tenant AES-256 · Tu Cuenta Única para Todos los LLMs</span>
  <h1>Conectá tu cuenta de impuesto.com.ar</h1>
  <p>Tu email es tu identidad única (como GitHub): vinculás tu CUIT una sola vez, obtenés tu enlace privado para Claude, ChatGPT, Gemini, Copilot o Cursor con <strong>historial compartido</strong>, y podés autorizar socios o analistas por email desde el chat sin compartir tu Clave Fiscal.</p>
  <form id="f">
    <label>Tu Email (dueño de la cuenta o email invitado)</label>
    <input id="email" name="email" type="email" placeholder="nombre@empresa.com" required>
    <label>Operación</label>
    <select id="modo" name="modo" onchange="toggleArca()">
      <option value="solo_lectura_cifrada">Vincular CUIT nuevo / actualizar Clave Fiscal (Modo Solo Lectura)</option>
      <option value="estudio_contable_delegado" {sel_estudio}>Estudio Contable B2B — Cartera Multi-Cliente</option>
      <option value="solo_token_llm">Ya tengo CUIT vinculado (o me invitaron por email) — Solo generar mi Token para otro LLM</option>
    </select>
    <div id="arcaFields">
      <label>CUIT (11 dígitos)</label>
      <input id="cuit" name="cuit" value="{cuit_val}" placeholder="20301234567" maxlength="13">
      <label>Clave Fiscal ARCA (cifrada en reposo, nunca visible en el chat)</label>
      <div class="pw-wrap">
        <input id="clave" name="clave_fiscal" type="password" placeholder="••••••••">
        <button type="button" class="pw-toggle" onclick="togglePw('clave', this)">Ver</button>
      </div>
    </div>
    <label>Frase clave personalizada para tu enlace privado (opcional · mín. 16 caracteres, letras + números)</label>
    <div class="pw-wrap">
      <input id="custom_token" name="token_personalizado" type="password" placeholder="Dejar vacío para generar automática (ej: Cafe-Cordoba-Fiscal-8924)" oninput="checkMatch()">
      <button type="button" class="pw-toggle" onclick="togglePw('custom_token', this)">Ver</button>
    </div>
    <div id="repeatWrap" style="display:none">
      <label>Repetir frase clave personalizada</label>
      <div class="pw-wrap">
        <input id="custom_token_2" type="password" placeholder="Volvé a escribir la misma frase clave" oninput="checkMatch()">
        <button type="button" class="pw-toggle" onclick="togglePw('custom_token_2', this)">Ver</button>
      </div>
      <div id="matchHint" class="hint"></div>
    </div>
    <label>Etiqueta del dispositivo / LLM (opcional)</label>
    <input id="label" name="etiqueta_token" placeholder="Ej: Gemini personal, Claude trabajo, ChatGPT">
    <button class="btn" type="submit">Vincular y generar mis enlaces privados</button>
    <div id="msg"></div>
  </form>
  <div id="urls" class="urls">
    <strong>✅ ¡Listo! Copiá tu enlace privado para el asistente que quieras usar:</strong>
    <div style="font-size:12.5px;color:#166534;margin-top:4px">Guardá este enlace en un lugar seguro. Podés usar el mismo en todos tus LLMs y mantener un historial unificado.</div>
    <div id="urlList"></div>
  </div>
  <div class="sec">
    <strong>Garantías de seguridad Multi-Tenant:</strong><br>
    • Aislamiento estricto: ningún otro usuario puede consultar tu CUIT aunque conozca el número.<br>
    • Cifrado en reposo AES + HMAC-SHA256; tokens guardados solo como hash SHA-256.<br>
    • Desde el chat podés autorizar o revocar socios/analistas por email en 1 segundo.
  </div>
</div>
<script>
function toggleArca() {{
  const m = document.getElementById('modo').value;
  document.getElementById('arcaFields').style.display = (m === 'solo_token_llm') ? 'none' : 'block';
}}
function togglePw(id, btn) {{
  const inp = document.getElementById(id);
  const show = inp.type === 'password';
  inp.type = show ? 'text' : 'password';
  btn.textContent = show ? 'Ocultar' : 'Ver';
}}
function checkMatch() {{
  const t1 = document.getElementById('custom_token').value.trim();
  const t2 = document.getElementById('custom_token_2').value.trim();
  const wrap = document.getElementById('repeatWrap');
  const hint = document.getElementById('matchHint');
  wrap.style.display = t1.length > 0 ? 'block' : 'none';
  if (!t1) {{ hint.textContent = ''; return true; }}
  if (t1.length < 16) {{
    hint.style.color = '#B45309';
    hint.textContent = 'Caracteres: ' + t1.length + '/16 (faltan ' + (16 - t1.length) + ')';
    return false;
  }}
  if (!t2) {{
    hint.style.color = '#475467';
    hint.textContent = 'Repetí la frase clave arriba para confirmar (' + t1.length + ' caracteres).';
    return false;
  }}
  if (t1 !== t2) {{
    hint.style.color = '#B42318';
    hint.textContent = '❌ Las frases clave no coinciden.';
    return false;
  }}
  hint.style.color = '#0B6E4F';
  hint.textContent = '✅ Las frases clave coinciden (' + t1.length + ' caracteres).';
  return true;
}}
document.getElementById('f').addEventListener('submit', async (e) => {{
  e.preventDefault();
  const msg = document.getElementById('msg');
  const urlsBox = document.getElementById('urls');
  urlsBox.style.display = 'none';
  const t1 = document.getElementById('custom_token').value.trim();
  if (t1 && !checkMatch()) {{
    msg.style.color = '#B42318';
    msg.textContent = '❌ Verificá que la frase clave tenga al menos 16 caracteres y coincida en ambos campos.';
    return;
  }}
  msg.style.color = '#0B1320';
  msg.textContent = 'Cifrando y generando acceso privado...';
  const res = await fetch('/api/v1/vincular', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{
      email: document.getElementById('email').value,
      cuit: document.getElementById('cuit').value,
      modo: document.getElementById('modo').value,
      clave_fiscal: document.getElementById('clave').value,
      token_personalizado: document.getElementById('custom_token').value,
      etiqueta_token: document.getElementById('label').value || 'web'
    }})
  }});
  const data = await res.json();
  if (data.ok) {{
    msg.style.color = '#0B6E4F';
    msg.textContent = '✅ Cuenta ' + (data.email || '') + (data.cuit ? ' · CUIT ' + data.cuit : '') + ' protegida con aislamiento privado.';
    document.getElementById('clave').value = '';
    if (data.urls_privadas_mcp) {{
      const list = document.getElementById('urlList');
      list.innerHTML = '';
      for (const [k, u] of Object.entries(data.urls_privadas_mcp)) {{
        const row = document.createElement('div');
        row.className = 'url-row';
        row.innerHTML = '<span style="overflow:hidden;text-overflow:ellipsis">' + k.toUpperCase() + ': ' + u + '</span>' +
          '<button type="button" class="copy">Copiar</button>';
        row.querySelector('button').onclick = () => {{ navigator.clipboard.writeText(u); row.querySelector('button').textContent = '¡Copiado!'; }};
        list.appendChild(row);
      }}
      urlsBox.style.display = 'block';
    }}
  }} else {{
    msg.style.color = '#B42318';
    msg.textContent = '❌ ' + (data.error || 'Error al vincular');
  }}
}});
</script>
</body>
</html>"""


@app.post("/api/v1/vincular")
def api_vincular(req: VincularRequest):
    email = normalizar_email(req.email or "")
    res: Dict[str, Any] = {"ok": True}

    if req.modo != "solo_token_llm":
        res = guardar_credenciales_cifradas(
            cuit=req.cuit or "",
            clave_fiscal=req.clave_fiscal,
            modo=req.modo,
            cert_pem=req.cert_pem,
            key_pem=req.key_pem,
            alias=req.alias,
            owner_email=email or None,
        )
        if not res.get("ok"):
            return res

    if email:
        tok = crear_token_usuario(
            email=email,
            label=req.etiqueta_token or "principal",
            custom_token=req.token_personalizado or None,
        )
        if not tok.get("ok"):
            return tok
        t = tok["token"]
        res["email"] = email
        res["token_id"] = tok["token_id"]
        res["token"] = t
        res["urls_privadas_mcp"] = {
            "gemini": f"https://gemini.impuesto.com.ar/?token={t}",
            "claude": f"https://claude.impuesto.com.ar/?token={t}",
            "chatgpt": f"https://chatgpt.impuesto.com.ar/?token={t}",
            "copilot": f"https://copilot.impuesto.com.ar/?token={t}",
            "cursor": f"https://cursor.impuesto.com.ar/?token={t}",
        }
        if res.get("cuit"):
            registrar_evento_historial(
                email=email,
                cuit=res["cuit"],
                origen_llm="portal_web",
                accion="vincular_cuit",
                titulo=f"CUIT {res['cuit']} vinculado bajo propiedad de {email}",
                detalle=f"Modo: {req.modo} · Token ID: {tok['token_id']}",
            )
    elif req.modo == "solo_token_llm":
        return {"ok": False, "error": "Ingresá tu email para generar tu token personal multi-LLM."}

    return res


@app.get("/api/v1/vincular/{cuit}")
def api_estado_vincular(cuit: str):
    return estado_vinculacion(cuit)


@app.delete("/api/v1/vincular/{cuit}")
def api_revocar_vincular(cuit: str):
    return revocar_credenciales(cuit)


@app.post("/api/v1/mcp/tool")
def run_mcp_tool(
    req: McpToolRequest,
    request: Request,
    x_bot_secret: Optional[str] = Header(default=None),
    x_user_token: Optional[str] = Header(default=None),
    x_llm_origin: Optional[str] = Header(default="mcp"),
):
    _check_secret(x_bot_secret)
    tool = req.name
    args = req.arguments or {}
    origen_llm = (x_llm_origin or "mcp").strip().lower()
    public_base = os.environ.get("PUBLIC_BOT_URL", "https://impuesto.com.ar").rstrip("/")

    # Resolver identidad multi-tenant del usuario
    actor_email = resolver_email_por_token(x_user_token)
    logger.info(f"[MCP] tool={tool} origin={origen_llm} user={actor_email or 'ANON'} keys={list(args.keys())}")

    # Herramientas 100% públicas (no tocan bóveda ni datos de ningún contribuyente)
    if tool == "verificar_estado_servidores_arca_ws":
        from .arca_ws import verificar_estado_servidores_wsfe
        return verificar_estado_servidores_wsfe(ambiente=args.get("ambiente", "produccion"))

    if tool == "verificar_proveedor_apocrifo_apoc":
        from .scraper_extras_arca import verificar_proveedor_apocrifo_apoc
        return verificar_proveedor_apocrifo_apoc(args.get("cuit_proveedor", ""))

    # =========================================================================
    # BARRERA ESTRICTA MULTI-TENANT: a partir de acá EXIGE token válido
    # =========================================================================
    if not actor_email:
        return _auth_required_error(public_base)

    # Herramientas de identidad, permisos (Owner -> invitados) e Historial Cross-LLM
    if tool == "listar_empresas":
        autorizados = listar_cuits_autorizados(actor_email)
        representadas = []
        with _audit_lock:
            for item in autorizados:
                cached = AUDIT_CACHE.get(item["cuit"])
                if cached and isinstance(cached.get("data"), dict):
                    sct = cached["data"].get("sct") or {}
                    if isinstance(sct.get("cuits_disponibles"), list):
                        representadas.extend(sct["cuits_disponibles"])
        if not autorizados:
            return {
                "ok": True,
                "usuario": actor_email,
                "origen_llm": origen_llm,
                "empresas_vinculadas": [],
                "requiere_vinculacion": True,
                "mensaje": f"Tu cuenta ({actor_email}) todavía no tiene CUITs vinculados ni autorizados. Vinculá tu CUIT en {public_base}/vincular o pedile al Owner que te autorice por email.",
                "url_vinculacion_segura": f"{public_base}/vincular",
            }
        return {
            "ok": True,
            "usuario": actor_email,
            "origen_llm": origen_llm,
            "empresas_vinculadas": autorizados,
            "cuits_representados_detectados": representadas,
            "nota": "Mostrando exclusivamente los CUITs donde sos Owner o fuiste autorizado explícitamente.",
        }

    if tool == "autorizar_usuario_cuit":
        out = autorizar_usuario_cuit(
            owner_email=actor_email,
            cuit=args.get("cuit", ""),
            email_invitado=args.get("email_invitado", ""),
            rol=args.get("rol", "solo_lectura"),
        )
        if out.get("ok"):
            registrar_evento_historial(
                email=actor_email,
                cuit=out["cuit"],
                origen_llm=origen_llm,
                accion="autorizar_usuario",
                titulo=f"Autorizó a {out['email_autorizado']} ({out['rol']})",
                detalle=f"CUIT {out['cuit']}",
            )
        return out

    if tool == "revocar_usuario_cuit":
        out = revocar_usuario_cuit(
            owner_email=actor_email,
            cuit=args.get("cuit", ""),
            email_invitado=args.get("email_invitado", ""),
        )
        if out.get("ok"):
            registrar_evento_historial(
                email=actor_email,
                cuit=out["cuit"],
                origen_llm=origen_llm,
                accion="revocar_usuario",
                titulo=f"Revocó acceso a {out['email_revocado']}",
                detalle=f"CUIT {out['cuit']}",
            )
        return out

    if tool == "listar_accesos_cuit":
        return listar_accesos_cuit(actor_email=actor_email, cuit=args.get("cuit", ""))

    if tool == "ver_historial_actividad":
        return obtener_historial_actividad(
            actor_email=actor_email,
            cuit=args.get("cuit", ""),
            limite=int(args.get("limite", 25)),
        )

    if tool == "registrar_nota_historial":
        cuit_nota = normalizar_cuit(args.get("cuit", ""))
        if cuit_nota:
            ok_p, _, reason = verificar_permiso_cuit(actor_email, cuit_nota, nivel="lectura")
            if not ok_p:
                return {"ok": False, "acceso_denegado": True, "error": reason}
        ev = registrar_evento_historial(
            email=actor_email,
            cuit=cuit_nota,
            origen_llm=origen_llm,
            accion="nota_contador",
            titulo=args.get("titulo", "Nota guardada"),
            detalle=args.get("detalle", ""),
        )
        return {"ok": True, "evento": ev, "mensaje": "Nota guardada en tu historial compartido multi-LLM (visible desde Claude, ChatGPT, Gemini, Copilot y Cursor)."}

    # Determinar nivel de permiso requerido (escritura solo si confirmado=True en acciones mutantes)
    es_escritura = (tool in ("emitir_factura_wsfe", "consultar_y_renovar_certificado_mipyme") and bool(args.get("confirmado", False)))
    nivel_req = "escritura" if es_escritura else "lectura"

    cuit, clave, err = _resolve_creds_authorized(actor_email, args, public_base, nivel=nivel_req)
    if err:
        return err

    if tool == "auditar_estado_integral_arca":
        return _ejecutar_auditoria_sin_timeout(
            cuit=cuit,
            clave=clave,
            forzar_refresco=bool(args.get("forzar_refresco", False)),
            actor_email=actor_email,
            origen_llm=origen_llm,
        )

    if tool == "consultar_ccma_cuenta_corriente":
        with _audit_lock:
            cached = AUDIT_CACHE.get(cuit)
            if cached and (time.time() - cached["ts"]) < AUDIT_TTL_SEC:
                ccma = (cached["data"] or {}).get("ccma")
                if ccma:
                    return {"ok": True, "cuit": cuit, "desde_cache": True, "ccma": ccma}
            if cuit in AUDIT_INFLIGHT:
                return _ejecutar_auditoria_sin_timeout(cuit=cuit, clave=clave, actor_email=actor_email, origen_llm=origen_llm)
        from .auditoria_unificada import consultar_ccma_preciso
        res = consultar_ccma_preciso(cuit=cuit, clave=clave)
        registrar_evento_historial(actor_email, cuit, origen_llm, "consulta_ccma", f"Consulta CCMA (CUIT {cuit})")
        return res

    if tool == "consultar_bienes_personales_web":
        from .scraper_bbpp import consultar_bienes_personales_web
        return _run_tool_sin_timeout(
            f"bbpp:{cuit}", "Bienes Personales Web (F. 762)",
            lambda: consultar_bienes_personales_web(usuario=cuit, clave=clave),
            cuit=cuit, actor_email=actor_email, origen_llm=origen_llm, accion_hist="consulta_bbpp",
        )

    if tool == "consultar_nuestra_parte_arca":
        from .scraper_extras_arca import consultar_nuestra_parte
        return _run_tool_sin_timeout(
            f"nuestraparte:{cuit}", "Nuestra Parte ARCA",
            lambda: consultar_nuestra_parte(usuario=cuit, clave=clave),
            cuit=cuit, actor_email=actor_email, origen_llm=origen_llm, accion_hist="consulta_nuestra_parte",
        )

    if tool == "consultar_mis_retenciones_arca":
        from .scraper_extras_arca import consultar_mis_retenciones
        obj = args.get("cuit_objetivo") or cuit
        return _run_tool_sin_timeout(
            f"retenciones:{cuit}:{obj}", "Mis Retenciones ARCA",
            lambda: consultar_mis_retenciones(usuario=cuit, clave=clave, cuit_objetivo=args.get("cuit_objetivo")),
            cuit=cuit, actor_email=actor_email, origen_llm=origen_llm, accion_hist="consulta_retenciones",
        )

    if tool == "consultar_y_renovar_certificado_mipyme":
        from .scraper_extras_arca import consultar_y_renovar_certificado_mipyme
        emp = args.get("cuit_empresa", cuit)
        conf = bool(args.get("confirmado", False))
        return _run_tool_sin_timeout(
            f"mipyme:{cuit}:{emp}:{conf}", "Certificado MiPyME (F. 1272)",
            lambda: consultar_y_renovar_certificado_mipyme(usuario=cuit, clave=clave, cuit_empresa=emp, confirmado=conf),
            cuit=cuit, actor_email=actor_email, origen_llm=origen_llm, accion_hist="consulta_mipyme",
        )

    if tool == "consultar_comprobantes_mes":
        import calendar
        import datetime as _dt
        periodo = (args.get("periodo") or "").strip()
        rango = (args.get("rango_fechas") or "").strip()
        if not rango and periodo and len(periodo) == 7 and periodo[4] == "-":
            try:
                yy, mm = int(periodo[:4]), int(periodo[5:7])
                last_day = calendar.monthrange(yy, mm)[1]
                rango = f"01/{mm:02d}/{yy} - {last_day:02d}/{mm:02d}/{yy}"
            except Exception:
                rango = ""
        if not rango:
            hoy = _dt.date.today()
            last_day = calendar.monthrange(hoy.year, hoy.month)[1]
            rango = f"01/{hoy.month:02d}/{hoy.year} - {last_day:02d}/{hoy.month:02d}/{hoy.year}"

        tipo_req = (args.get("tipo") or "ambos").lower()
        def _fetch_mc():
            if tipo_req == "ambos":
                em = consultar_mis_comprobantes(cuit=cuit, usuario=cuit, clave=clave, tipo="E", rango_fechas=rango)
                rec = consultar_mis_comprobantes(cuit=cuit, usuario=cuit, clave=clave, tipo="R", rango_fechas=rango)
                return {
                    "ok": True,
                    "cuit": cuit,
                    "periodo": periodo or rango,
                    "rango_fechas": rango,
                    "tipo": "ambos",
                    "cantidad_emitidos": len(em),
                    "cantidad_recibidos": len(rec),
                    "emitidos": em,
                    "recibidos": rec,
                }
            t_code = "E" if tipo_req == "emitidos" else "R"
            rows = consultar_mis_comprobantes(cuit=cuit, usuario=cuit, clave=clave, tipo=t_code, rango_fechas=rango)
            return {
                "ok": True,
                "cuit": cuit,
                "periodo": periodo or rango,
                "rango_fechas": rango,
                "tipo": tipo_req,
                "cantidad": len(rows),
                "comprobantes": rows,
            }

        return _run_tool_sin_timeout(
            f"comprobantes:{cuit}:{tipo_req}:{rango}",
            f"Mis Comprobantes {periodo or rango} ({tipo_req})",
            _fetch_mc,
            cuit=cuit, actor_email=actor_email, origen_llm=origen_llm, accion_hist="consulta_comprobantes",
        )

    if tool == "leer_notificaciones_dfe":
        from .scraper import consultar_notificaciones_dfe
        obj = args.get("cuit") or cuit
        return _run_tool_sin_timeout(
            f"dfe:{cuit}:{obj}", "Domicilio Fiscal Electrónico (DFE)",
            lambda: {"ok": True, "cuit": obj, "notificaciones": consultar_notificaciones_dfe(usuario=cuit, clave=clave, cuit_objetivo=args.get("cuit"))},
            cuit=cuit, actor_email=actor_email, origen_llm=origen_llm, accion_hist="consulta_dfe",
        )

    if tool in ("consultar_estado_monotributo", "consultar_situacion_monotributo"):
        with _audit_lock:
            cached = AUDIT_CACHE.get(cuit)
            if cached and (time.time() - cached["ts"]) < AUDIT_TTL_SEC:
                mono = (cached["data"] or {}).get("portal_monotributo")
                if mono:
                    return {"ok": True, "cuit": cuit, "desde_cache": True, "portal_monotributo": mono}
        return _ejecutar_auditoria_sin_timeout(cuit=cuit, clave=clave, actor_email=actor_email, origen_llm=origen_llm)

    if tool == "consultar_padron_cuit_ws":
        from .arca_ws import consultar_padron_a5
        return consultar_padron_a5(cuit_consulta=args.get("cuit_consulta", cuit), cuit_representado=cuit, ambiente=args.get("ambiente", "produccion"))

    if tool == "emitir_factura_wsfe":
        from .arca_ws import emitir_comprobante_wsfe
        res = emitir_comprobante_wsfe(
            cuit_emisor=args.get("cuit_emisor", cuit),
            pto_vta=int(args.get("pto_vta", 1)),
            cbte_tipo=int(args.get("cbte_tipo", 11)),
            receptor_cuit=args.get("receptor_cuit", ""),
            importe_neto=float(args.get("importe_neto", 0)),
            importe_iva=float(args.get("importe_iva", 0)),
            concepto=int(args.get("concepto", 2)),
            ambiente=args.get("ambiente", "homologacion"),
            confirmado=bool(args.get("confirmado", False)),
            cbte_asoc=args.get("cbte_asoc"),
            condicion_iva_receptor_id=args.get("condicion_iva_receptor_id"),
        )
        if bool(args.get("confirmado", False)):
            registrar_evento_historial(actor_email, cuit, origen_llm, "emitir_factura_wsfe", f"Factura WSFE a {args.get('receptor_cuit','')} por ${args.get('importe_neto',0)}")
        return res

    if tool == "generar_certificado_csr_arca":
        from .arca_ws import generar_csr_arca
        return generar_csr_arca(cuit=args.get("cuit", cuit), razon_social=args.get("razon_social", "Contribuyente"), alias=args.get("alias", "impuesto_mcp"))

    return {"ok": False, "error": f"Herramienta '{tool}' no mapeada aún en el backend headless."}


def run_job(job_id: str, params: AutomationParams):
    jobs[job_id]["status"] = "in_process"
    try:
        data = consultar_mis_comprobantes(
            cuit=params.cuit,
            usuario=params.username,
            clave=params.password,
            tipo=params.filters.t,
            rango_fechas=params.filters.fechaEmision,
        )
        jobs[job_id]["status"] = "complete"
        jobs[job_id]["data"] = data
    except Exception as e:
        logger.exception(f"Error en trabajo {job_id}")
        jobs[job_id]["status"] = "error"
        jobs[job_id]["message"] = str(e)


@app.post("/api/v1/automations")
def start_automation(req: StartRequest):
    if req.automation != "mis-comprobantes":
        raise HTTPException(status_code=400, detail="Automatización desconocida")
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"id": job_id, "status": "in_process", "created_at": time.time(), "data": [], "message": ""}
    executor.submit(run_job, job_id, req.params)
    return {"id": job_id, "status": "in_process"}


@app.get("/api/v1/automations/{job_id}")
def get_automation_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    now = time.time()
    for k in [k for k, v in jobs.items() if now - v.get("created_at", now) > 3600]:
        jobs.pop(k, None)
    return {"id": job["id"], "status": job["status"], "data": job.get("data", []), "message": job.get("message", "")}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot.main:app", host="0.0.0.0", port=8000, reload=True)
