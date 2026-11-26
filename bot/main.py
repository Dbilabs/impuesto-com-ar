"""
bot/main.py
Microservicio Backend Headless de impuesto.com.ar (BOT_API_URL).

Expone:
  - GET  /health                    -> Estado del servicio
  - GET  /vincular                  -> Portal cifrado de vinculación única (WSAA o Solo Lectura)
  - POST /api/v1/vincular           -> Guarda credenciales/certificados cifrados (AES + HMAC-SHA256)
  - GET  /api/v1/vincular/{cuit}    -> Verifica estado de vinculación (nunca expone secretos)
  - DELETE /api/v1/vincular/{cuit}  -> Revoca acceso en 1 clic
  - POST /api/v1/mcp/tool           -> Ejecutor headless llamado por los 8 subdominios MCP
  - POST /api/v1/automations        -> Compatibilidad con jobs asíncronos de Mis Comprobantes
"""

import os
import uuid
import time
import logging
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
    normalizar_cuit,
)
from .auditoria_unificada import auditar_estado_integral_arca

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("arca_api")

app = FastAPI(title="impuesto.com.ar — ARCA Headless Engine", version="2.2.0")
executor = ThreadPoolExecutor(max_workers=3)
jobs: Dict[str, Dict[str, Any]] = {}


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
    cuit: str
    clave_fiscal: Optional[str] = None
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


def _resolve_creds(args: Dict[str, Any], public_base_url: str):
    cuit = normalizar_cuit(args.get("cuit") or args.get("cuit_empresa") or args.get("cuit_emisor") or args.get("usuario") or "")
    if not cuit:
        return None, None, {
            "ok": False,
            "requiere_vinculacion": True,
            "mensaje": "Indicame tu CUIT (11 dígitos) para consultar en modo solo lectura desde la bóveda segura.",
            "url_vinculacion_segura": f"{public_base_url}/vincular",
        }
    rec = obtener_credenciales_descifradas(cuit)
    if rec and rec.get("clave_fiscal"):
        return cuit, rec["clave_fiscal"], None
    return cuit, None, {
        "ok": False,
        "requiere_vinculacion": True,
        "cuit": cuit,
        "mensaje": (
            f"El CUIT {cuit} todavía no está vinculado a tu bóveda segura. "
            f"Vinculalo una sola vez en {public_base_url}/vincular (cifrado AES + modo solo lectura, "
            "o mediante Certificado Digital WSAA sin compartir tu Clave Fiscal). "
            "Así todas tus consultas corren en segundo plano dentro del chat, sin abrir nunca Chrome."
        ),
        "url_vinculacion_segura": f"{public_base_url}/vincular?cuit={cuit}",
    }


@app.get("/health")
def health():
    return {"status": "ok", "version": "2.2.0", "mode": "headless_vault", "active_jobs": len(jobs)}


@app.get("/vincular", response_class=HTMLResponse)
def vincular_page(cuit: str = "", tipo: str = ""):
    cuit_val = normalizar_cuit(cuit)
    is_estudio = tipo.lower() == "estudio"
    sel_estudio = "selected" if is_estudio else ""
    return f"""<!doctype html>
<html lang="es-AR">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vinculación Segura ARCA — impuesto.com.ar</title>
<style>
:root{{--ink:#0B1320;--muted:#475467;--line:#E3E7EC;--bg:#F8FAFC;--acc:#0B6E4F;--acc2:#074F39;--tint:#E7F5EF;--font:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
*{{box-sizing:border-box}} body{{margin:0;font-family:var(--font);color:var(--ink);background:var(--bg);padding:40px 20px;line-height:1.6}}
.card{{max-width:560px;margin:0 auto;background:#fff;border:1px solid var(--line);border-radius:18px;padding:34px;box-shadow:0 14px 36px rgba(15,27,45,.07)}}
.badge{{background:var(--tint);color:var(--acc2);font-weight:700;font-size:12px;padding:4px 12px;border-radius:99px;display:inline-block;margin-bottom:12px}}
h1{{margin:0 0 8px;font-size:25px;letter-spacing:-.02em}} p{{color:var(--muted);font-size:14.5px;margin:0 0 20px}}
label{{display:block;font-weight:600;font-size:13.5px;margin:12px 0 6px}}
input,select{{width:100%;padding:11px 13px;border:1px solid #CBD5E1;border-radius:10px;font-size:15px}}
.btn{{margin-top:20px;width:100%;background:var(--acc);color:#fff;border:0;padding:13px;border-radius:10px;font-weight:700;font-size:15px;cursor:pointer}}
.btn:hover{{background:var(--acc2)}}
.sec{{margin-top:18px;background:#F8FAFC;border:1px solid var(--line);border-radius:12px;padding:14px;font-size:13px;color:var(--muted)}}
.sec strong{{color:var(--ink)}} #msg{{margin-top:14px;font-weight:600;font-size:14px}}
</style>
</head>
<body>
<div class="card">
  <span class="badge">🔒 Bóveda Cifrada AES-256 · Modo Solo Lectura</span>
  <h1>Vinculá tu CUIT con impuesto.com.ar</h1>
  <p>Vinculá tu acceso una sola vez (contribuyente individual, PyME o Estudio Contable) para que tu Contador Agéntico en Claude, ChatGPT o Gemini audite ARCA 100% en segundo plano dentro del chat, sin abrir nunca ventanas emergentes.</p>
  <form id="f">
    <label>CUIT (personal, sociedad o CUIT del Estudio Contable)</label>
    <input id="cuit" name="cuit" value="{cuit_val}" placeholder="20301234567" required maxlength="13">
    <label>Tipo de vinculación</label>
    <select id="modo" name="modo">
      <option value="solo_lectura_cifrada">Contribuyente / PyME — Modo Solo Lectura Cifrado</option>
      <option value="estudio_contable_delegado" {sel_estudio}>Estudio Contable B2B — Cartera Multi-Cliente (vía delegaciones ARCA)</option>
      <option value="delegacion_wsaa">Certificado Digital WSAA (sin Clave Fiscal)</option>
    </select>
    <label>Clave Fiscal ARCA (cifrada en reposo, nunca visible en el chat)</label>
    <input id="clave" name="clave_fiscal" type="password" placeholder="••••••••" required>
    <button class="btn" type="submit">Vincular de forma segura</button>
    <div id="msg"></div>
  </form>
  <div class="sec">
    <strong>Garantías de seguridad:</strong><br>
    • Cifrado en reposo AES + HMAC-SHA256.<br>
    • Operación 100% solo lectura por defecto (ninguna factura, DDJJ ni plan se envía sin tu confirmación explícita).<br>
    • Podés revocar el acceso en cualquier momento con un clic o cambiando tu Clave Fiscal en ARCA.
  </div>
</div>
<script>
document.getElementById('f').addEventListener('submit', async (e) => {{
  e.preventDefault();
  const msg = document.getElementById('msg');
  msg.textContent = 'Cifrando y guardando...';
  const res = await fetch('/api/v1/vincular', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{
      cuit: document.getElementById('cuit').value,
      modo: document.getElementById('modo').value,
      clave_fiscal: document.getElementById('clave').value
    }})
  }});
  const data = await res.json();
  if (data.ok) {{
    msg.style.color = '#0B6E4F';
    msg.textContent = '✅ CUIT ' + data.cuit + ' vinculado con cifrado seguro. Volvé a tu chat en Claude/ChatGPT y decile: "Ya vinculé mi CUIT, hagamos la auditoría 360°".';
    document.getElementById('clave').value = '';
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
    return guardar_credenciales_cifradas(
        cuit=req.cuit,
        clave_fiscal=req.clave_fiscal,
        modo=req.modo,
        cert_pem=req.cert_pem,
        key_pem=req.key_pem,
        alias=req.alias,
    )


@app.get("/api/v1/vincular/{cuit}")
def api_estado_vincular(cuit: str):
    return estado_vinculacion(cuit)


@app.delete("/api/v1/vincular/{cuit}")
def api_revocar_vincular(cuit: str):
    return revocar_credenciales(cuit)


@app.post("/api/v1/mcp/tool")
def run_mcp_tool(req: McpToolRequest, request: Request, x_bot_secret: Optional[str] = Header(default=None)):
    _check_secret(x_bot_secret)
    tool = req.name
    args = req.arguments or {}
    public_base = os.environ.get("PUBLIC_BOT_URL", "https://impuesto.com.ar").rstrip("/")

    # Herramientas sin clave fiscal (públicas / WS)
    if tool == "verificar_estado_servidores_arca_ws":
        from .arca_ws import verificar_estado_servidores_wsfe
        return verificar_estado_servidores_wsfe(ambiente=args.get("ambiente", "produccion"))

    if tool == "verificar_proveedor_apocrifo_apoc":
        from .scraper_extras_arca import verificar_proveedor_apocrifo_apoc
        return verificar_proveedor_apocrifo_apoc(args.get("cuit_proveedor", ""))

    # Herramientas que requieren acceso ARCA desde la Bóveda Cifrada (cero popups)
    cuit, clave, err = _resolve_creds(args, public_base)
    if err:
        return err

    if tool == "auditar_estado_integral_arca":
        return auditar_estado_integral_arca(cuit=cuit, clave=clave)

    if tool == "consultar_ccma_cuenta_corriente":
        from .auditoria_unificada import consultar_ccma_preciso
        return consultar_ccma_preciso(cuit=cuit, clave=clave)

    if tool == "consultar_bienes_personales_web":
        from .scraper_bbpp import consultar_bienes_personales_web
        return consultar_bienes_personales_web(usuario=cuit, clave=clave)

    if tool == "consultar_nuestra_parte_arca":
        from .scraper_extras_arca import consultar_nuestra_parte
        return consultar_nuestra_parte(usuario=cuit, clave=clave)

    if tool == "consultar_mis_retenciones_arca":
        from .scraper_extras_arca import consultar_mis_retenciones
        return consultar_mis_retenciones(usuario=cuit, clave=clave, cuit_objetivo=args.get("cuit_objetivo"))

    if tool == "consultar_y_renovar_certificado_mipyme":
        from .scraper_extras_arca import consultar_y_renovar_certificado_mipyme
        return consultar_y_renovar_certificado_mipyme(
            usuario=cuit, clave=clave, cuit_empresa=args.get("cuit_empresa", cuit), confirmado=bool(args.get("confirmado", False))
        )

    if tool == "consultar_comprobantes_mes":
        return consultar_mis_comprobantes(
            cuit=cuit,
            usuario=cuit,
            clave=clave,
            tipo="E" if args.get("tipo") == "emitidos" else "R",
            rango_fechas=args.get("rango_fechas", ""),
        )

    if tool == "leer_notificaciones_dfe":
        from .scraper import consultar_notificaciones_dfe
        return {"ok": True, "notificaciones": consultar_notificaciones_dfe(usuario=cuit, clave=clave, cuit_objetivo=args.get("cuit"))}

    if tool == "consultar_estado_monotributo":
        from .scraper_monotributo import consultar_estado_monotributo
        return consultar_estado_monotributo(usuario=cuit, clave=clave)

    if tool == "consultar_padron_cuit_ws":
        from .arca_ws import consultar_padron_a5
        return consultar_padron_a5(cuit_consulta=args.get("cuit_consulta", cuit), cuit_representado=cuit, ambiente=args.get("ambiente", "produccion"))

    if tool == "emitir_factura_wsfe":
        from .arca_ws import emitir_comprobante_wsfe
        return emitir_comprobante_wsfe(
            cuit_emisor=args.get("cuit_emisor", cuit),
            pto_vta=int(args.get("pto_vta", 1)),
            cbte_tipo=int(args.get("cbte_tipo", 11)),
            receptor_cuit=args.get("receptor_cuit", ""),
            importe_neto=float(args.get("importe_neto", 0)),
            importe_iva=float(args.get("importe_iva", 0)),
            concepto=int(args.get("concepto", 2)),
            ambiente=args.get("ambiente", "homologacion"),
            confirmado=bool(args.get("confirmado", False)),
        )

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
