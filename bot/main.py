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
import hashlib
import secrets
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
    es_admin_plataforma,
    esta_usuario_suspendido,
    revocar_tokens_usuario,
    admin_resumen_plataforma,
    admin_listar_clientes,
    admin_ver_movimientos,
    admin_gestionar_suscripcion,
    solicitar_codigo_otp_email,
    verificar_codigo_otp_email,
    obtener_huella_vault_key,
    marcar_cuit_validado,
    liberar_cuit_pendiente,
    es_owner_validado,
    cargar_presupuesto_cuit,
    guardar_presupuesto_cuit,
    hash_clave_cuit,
    verificar_y_marcar_refresco_no_validado,
    limpiar_refresco_no_validado,
)
from .arca_errors import ArcaNoDisponible, LoginNoConfirmado, ClaveIncorrecta
try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
except Exception:
    PlaywrightTimeoutError = TimeoutError
_TIMEOUT_TYPES = (TimeoutError, PlaywrightTimeoutError)
from .backoffice_growth import (
    esta_en_mantenimiento,
    obtener_anuncio_global_activo,
    admin_metricas_growth_saas,
    admin_detectar_oportunidades_y_riesgo,
    admin_gestionar_feature_flags_y_limites,
    admin_gestionar_cupones_y_referidos,
    admin_gestionar_soporte_y_anuncios,
    admin_exportar_reporte_inversor_markdown,
)
from .auditoria_unificada import auditar_estado_integral_arca

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("arca_api")

app = FastAPI(title="impuesto.com.ar — ARCA Headless Multi-Tenant Engine", version="3.3.0")
executor = ThreadPoolExecutor(max_workers=8)
PLAYWRIGHT_SEM = threading.Semaphore(int(os.environ.get("MAX_CONCURRENT_BROWSERS", "1")))
jobs: Dict[str, Dict[str, Any]] = {}

# Caché TTL (15 min) + deduplicación + circuit breaker de Clave Fiscal incorrecta (P0-7)
AUDIT_TTL_SEC = int(os.environ.get("AUDIT_CACHE_TTL_SEC", "900"))
ERROR_TTL_SEC = int(os.environ.get("AUDIT_ERROR_TTL_SEC", "60"))
AUDIT_SYNC_WAIT_SEC = float(os.environ.get("AUDIT_SYNC_WAIT_SEC", "5.0"))
INFLIGHT_MAX_AGE_SEC = int(os.environ.get("INFLIGHT_MAX_AGE_SEC", "300"))
_audit_lock = threading.RLock()
_cuit_locks: Dict[str, threading.Lock] = {}
AUDIT_CACHE: Dict[str, Dict[str, Any]] = {}
AUDIT_INFLIGHT: Dict[str, Dict[str, Any]] = {}
TOOL_CACHE: Dict[str, Dict[str, Any]] = {}
TOOL_INFLIGHT: Dict[str, Dict[str, Any]] = {}
_BAD_CREDS_CB: Dict[str, Dict[str, Any]] = {}
_CUIT_FAIL_BUDGET: Dict[str, list] = {}
CUIT_MAX_FAILS_24H = int(os.environ.get("CUIT_MAX_FAILS_24H", "2"))
_wsfe_locks: Dict[str, threading.Lock] = {}
_WSFE_IDEM_CACHE: Dict[str, Dict[str, Any]] = {}
LOCK_ACQUIRE_TIMEOUT_SEC = float(os.environ.get("LOCK_ACQUIRE_TIMEOUT_SEC", "180.0"))


def _get_wsfe_lock(cuit: str, pto_vta: int, cbte_tipo: int) -> threading.Lock:
    key = f"{cuit}:{pto_vta}:{cbte_tipo}"
    with _audit_lock:
        lk = _wsfe_locks.get(key)
        if lk is None:
            lk = threading.Lock()
            _wsfe_locks[key] = lk
        return lk


def _extract_client_ip(request: Optional[Request]) -> str:
    if not request:
        return "unknown"
    cf_ip = (request.headers.get("cf-connecting-ip") or request.headers.get("x-client-ip") or "").strip()
    if cf_ip:
        return cf_ip
    xff = (request.headers.get("x-forwarded-for") or "").strip()
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return (request.client.host if request.client else "unknown") or "unknown"


def _parse_bool_strict(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() == "true"
    return False


def _hash_clave(cuit: str, clave: str) -> str:
    return hash_clave_cuit(cuit, clave)


def _load_budget_locked(cuit: str, now: float) -> list:
    """Carga presupuesto persistido en volumen (N1-d) y purga entradas >24h."""
    disk = {}
    try:
        disk = cargar_presupuesto_cuit() or {}
    except Exception as exc:
        logger.error("Error leyendo presupuesto persistido de fallos CUIT %s: %s", cuit, exc, exc_info=True)
        disk = {}
    mem_fails = _CUIT_FAIL_BUDGET.get(cuit, [])
    disk_fails = disk.get(cuit, [])
    merged = sorted({float(t) for t in (mem_fails + disk_fails) if now - float(t) < 86400.0})
    if merged:
        _CUIT_FAIL_BUDGET[cuit] = merged
    else:
        _CUIT_FAIL_BUDGET.pop(cuit, None)
    return merged


def _save_budget_locked(cuit: str, fails: list) -> None:
    try:
        disk = cargar_presupuesto_cuit() or {}
        if fails:
            disk[cuit] = fails
        else:
            disk.pop(cuit, None)
        guardar_presupuesto_cuit(disk)
    except Exception as exc:
        logger.error("Error persistiendo presupuesto de fallos CUIT %s en bóveda: %s", cuit, exc, exc_info=True)


def _check_cuit_fail_budget(cuit: str) -> Optional[Dict[str, Any]]:
    """N1 cierre total: presupuesto persistido de máx. 2 logins fallidos cada 24h por CUIT (independiente de la clave)."""
    c = normalizar_cuit(cuit)
    now = time.time()
    with _audit_lock:
        fails = _load_budget_locked(c, now)
        if len(fails) >= CUIT_MAX_FAILS_24H:
            return {
                "ok": False,
                "estado": "PRESUPUESTO_FALLOS_CUIT_AGOTADO",
                "cuit": c,
                "circuit_breaker_activo": True,
                "error": f"El CUIT {c} alcanzó el máximo de {CUIT_MAX_FAILS_24H} logins fallidos en 24h.",
                "mensaje": (
                    f"Por seguridad, frenamos nuevos intentos de login contra ARCA para el CUIT {c} durante 24 horas "
                    "para evitar el bloqueo de la Clave Fiscal. Si sos el titular validado, reintentá más tarde o contactá a soporte."
                ),
            }
    return None


def _check_bad_creds(cuit: str, clave: str) -> Optional[Dict[str, Any]]:
    """Circuit breaker P0-7 + N1: frena logins repetidos por presupuesto 24h del CUIT o misma clave rechazada."""
    budget_err = _check_cuit_fail_budget(cuit)
    if budget_err:
        return budget_err
    h = _hash_clave(cuit, clave)
    with _audit_lock:
        rec = _BAD_CREDS_CB.get(cuit)
        if rec and rec.get("clave_hash") == h:
            return {
                "ok": False,
                "estado": rec.get("estado", "CLAVE_FISCAL_INCORRECTA"),
                "cuit": cuit,
                "circuit_breaker_activo": True,
                "error": rec.get("error", "Clave Fiscal rechazada por ARCA."),
                "mensaje": (
                    f"Frenamos los intentos automáticos para el CUIT {cuit} para proteger tu cuenta contra el bloqueo de Clave Fiscal en ARCA. "
                    "Actualizá tu Clave Fiscal correcta en el chat (`vincular_cuenta_en_chat`) o en https://impuesto.com.ar/vincular para reanudar."
                ),
            }
    return None


def _registrar_fallo_presupuesto_cuit(cuit: str) -> list:
    c = normalizar_cuit(cuit)
    now = time.time()
    with _audit_lock:
        fails = _load_budget_locked(c, now)
        fails.append(now)
        _CUIT_FAIL_BUDGET[c] = fails
        _save_budget_locked(c, fails)
        return list(fails)


def _mark_bad_creds(cuit: str, clave: str, err_msg: str, *, cambio_clave: bool = False) -> None:
    c = normalizar_cuit(cuit)
    now = time.time()
    u = (err_msg or "").upper()
    estado = "CLAVE_FISCAL_BLOQUEADA" if "BLOQUEADA" in u else "CLAVE_FISCAL_INCORRECTA"
    with _audit_lock:
        _BAD_CREDS_CB[c] = {
            "clave_hash": _hash_clave(c, clave),
            "estado": estado,
            "error": err_msg[:300],
            "ts": now,
        }
        fails = _load_budget_locked(c, now)
        fails.append(now)
        _CUIT_FAIL_BUDGET[c] = fails
        _save_budget_locked(c, fails)
    # N1-b / N1-f: liberar CUIT pendiente solo si la clave fallida coincide y nunca ante CAMBIO DE CLAVE
    if not cambio_clave and "CAMBIO DE CLAVE" not in u:
        liberar_cuit_pendiente(c, clave_fallida=clave)


def _mark_login_no_confirmado(cuit: str, clave: str, err_msg: str, actor_email: str = "") -> None:
    """N1-h: post-contraseña sin llegar a portalcf. Descuenta presupuesto pero NO crea circuit breaker de 'incorrecta' para un owner validado."""
    c = normalizar_cuit(cuit)
    _registrar_fallo_presupuesto_cuit(c)
    if not es_owner_validado(actor_email, c):
        liberar_cuit_pendiente(c, clave_fallida=clave)


def _clear_bad_creds(cuit: str, *, clear_budget: bool = False) -> None:
    c = normalizar_cuit(cuit)
    with _audit_lock:
        _BAD_CREDS_CB.pop(c, None)
        if clear_budget:
            _CUIT_FAIL_BUDGET.pop(c, None)
            _save_budget_locked(c, [])
            try:
                limpiar_refresco_no_validado(c)
            except Exception as exc:
                logger.error("Error limpiando cooldown de refresco CUIT %s: %s", c, exc, exc_info=True)
        AUDIT_CACHE.pop(c, None)
        for k in [k for k in TOOL_CACHE if c in k]:
            TOOL_CACHE.pop(k, None)


def _hay_login_en_curso(cuit: str) -> bool:
    """N1-g: True si existe una auditoría o tool autenticada ARCA en curso (no vencida) para `cuit`."""
    c = normalizar_cuit(cuit)
    if not c:
        return False
    now = time.time()
    with _audit_lock:
        inf = AUDIT_INFLIGHT.get(c)
        if inf is not None:
            if (now - inf.get("started_at", now)) <= INFLIGHT_MAX_AGE_SEC:
                return True
            AUDIT_INFLIGHT.pop(c, None)
        for k, tinf in list(TOOL_INFLIGHT.items()):
            if not tinf.get("usa_login", True):
                continue
            t_cuit = normalizar_cuit(tinf.get("cuit") or "")
            if t_cuit == c or (f":{c}" in k and (k.endswith(f":{c}") or f":{c}:" in k)):
                if (now - tinf.get("started_at", now)) <= INFLIGHT_MAX_AGE_SEC:
                    return True
                TOOL_INFLIGHT.pop(k, None)
    return False


def _invalidar_cache_cuit(cuit: str) -> None:
    """Invalida caché de auditoría/tools para un CUIT al guardar clave nueva (N1-b) sin tocar el presupuesto 24h."""
    c = normalizar_cuit(cuit)
    with _audit_lock:
        AUDIT_CACHE.pop(c, None)
        for k in [k for k in TOOL_CACHE if c in k]:
            TOOL_CACHE.pop(k, None)


def _get_cuit_lock(cuit: str) -> threading.Lock:
    with _audit_lock:
        lk = _cuit_locks.get(cuit)
        if lk is None:
            lk = threading.Lock()
            _cuit_locks[cuit] = lk
        return lk


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
    is_prod = bool(
        os.environ.get("FLY_APP_NAME", "").strip()
        or os.environ.get("RAILWAY_ENVIRONMENT", "").strip()
        or os.environ.get("REQUIRE_BOT_SECRET", "").strip() == "1"
    )
    if not expected:
        if is_prod:
            raise HTTPException(status_code=503, detail="BOT_API_SECRET not configured in production")
        return
    provided = (x_bot_secret or "").strip()
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Unauthorized BOT_API_SECRET")


def _extract_user_token(x_user_token: Optional[str], authorization: Optional[str]) -> str:
    t = (x_user_token or "").strip()
    if t:
        return t
    auth = (authorization or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _auth_required_error(public_base: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "requiere_autenticacion": True,
        "acceso_denegado": True,
        "mensaje": (
            "Para consultar ARCA o tu historial primero iniciá sesión acá mismo en el chat (sin salir a ninguna web): "
            "si ya tenés cuenta pasame tu email y tu frase clave (`iniciar_sesion_en_chat`); "
            "si es tu primera vez pasame tu email, CUIT, Clave Fiscal y una frase clave personal de mín. 16 caracteres (`vincular_cuenta_en_chat`). "
            f"(Opcional: si preferís no escribir tu Clave Fiscal en el chat, podés usar {public_base}/vincular)."
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


def _is_bad_cred_error(err_str: str) -> bool:
    u = (err_str or "").upper()
    return any(
        k in u
        for k in (
            "CLAVE_FISCAL_INCORRECTA",
            "CLAVE_FISCAL_BLOQUEADA",
            "CAMBIO DE CLAVE",
            "CAPTCHA",
        )
    )


def _clasificar_error_arca(exc: Exception, err_str: str, cuit: str, actor_email: str) -> str:
    """N1-h: clasifica fallos de login en ARCA por etapa y tipo de excepción.

    Retorna:
      - 'clave_incorrecta': presupuesto + circuit breaker.
      - 'login_no_confirmado': presupuesto, sin circuit breaker de 'incorrecta' para owner validado.
      - 'arca_no_disponible': sin presupuesto ni circuit breaker.
    """
    if isinstance(exc, ClaveIncorrecta):
        return "clave_incorrecta"
    if isinstance(exc, ArcaNoDisponible):
        return "arca_no_disponible"
    if isinstance(exc, LoginNoConfirmado):
        return "login_no_confirmado"
    if _is_bad_cred_error(err_str):
        return "clave_incorrecta"

    low = (err_str or "").lower()
    is_timeout = isinstance(exc, _TIMEOUT_TYPES) or type(exc).__name__ == "TimeoutError"

    post_pw_markers = ("portalcf.cloud", "f1:btningresar", "f1:password")
    pre_pw_markers = ("page.goto", "navigating to", "f1:username", "f1:btnsiguiente", "net::err_")

    if any(k in low for k in post_pw_markers):
        return "login_no_confirmado"
    if is_timeout and any(k in low for k in pre_pw_markers):
        return "arca_no_disponible"
    if is_timeout and not es_owner_validado(actor_email, cuit):
        return "login_no_confirmado"
    return "arca_no_disponible"


def _run_auditoria_background(
    cuit: str,
    clave: str,
    entry: Dict[str, Any],
    actor_email: str = "",
    origen_llm: str = "mcp",
    clave_hash: str = "",
) -> None:
    effective_clave_hash = clave_hash or _hash_clave(cuit, clave)
    cuit_lk = _get_cuit_lock(cuit)
    got_cuit = cuit_lk.acquire(timeout=LOCK_ACQUIRE_TIMEOUT_SEC)
    got_sem = False
    try:
        if not got_cuit:
            raise ArcaNoDisponible(f"Timeout esperando lock del CUIT {cuit} (otra consulta en curso).")
        # P0-7 cierre total: re-chequear circuit breaker DESPUÉS de adquirir el lock del CUIT
        cb_err = _check_bad_creds(cuit, clave)
        if cb_err:
            now = time.time()
            with _audit_lock:
                entry["result"] = cb_err
                entry["finished_at"] = now
                AUDIT_CACHE[cuit] = {"ts": now, "is_error": True, "data": cb_err}
                if AUDIT_INFLIGHT.get(cuit) is entry:
                    AUDIT_INFLIGHT.pop(cuit, None)
            return
        got_sem = PLAYWRIGHT_SEM.acquire(timeout=LOCK_ACQUIRE_TIMEOUT_SEC)
        if not got_sem:
            raise ArcaNoDisponible("Timeout esperando disponibilidad del motor headless ARCA.")
        res = auditar_estado_integral_arca(cuit=cuit, clave=clave)
        now = time.time()
        # N1-g: confirmar propiedad del CUIT vinculada a (actor_email, clave_hash); si fue pisada, restaura al actor exitoso
        if isinstance(res, dict) and (res.get("ok") is True or res.get("doublecheck", {}).get("fuentes_verificadas")):
            if marcar_cuit_validado(
                cuit,
                email_actor=actor_email,
                clave_hash=effective_clave_hash,
                clave_fiscal=clave,
            ):
                _clear_bad_creds(cuit, clear_budget=True)
        with _audit_lock:
            entry["result"] = res
            entry["finished_at"] = now
            AUDIT_CACHE[cuit] = {"ts": now, "is_error": (isinstance(res, dict) and res.get("ok") is False), "data": res}
            if AUDIT_INFLIGHT.get(cuit) is entry:
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
        now = time.time()
        err_str = str(e)
        cat = _clasificar_error_arca(e, err_str, cuit, actor_email)
        if cat == "clave_incorrecta":
            cambio_clave = isinstance(e, ClaveIncorrecta) and bool(e.cambio_clave)
            bloqueada = (isinstance(e, ClaveIncorrecta) and bool(e.bloqueada)) or ("BLOQUEADA" in err_str.upper())
            _mark_bad_creds(cuit, clave, err_str, cambio_clave=cambio_clave)
            err_obj = {
                "ok": False,
                "estado": "CLAVE_FISCAL_BLOQUEADA" if bloqueada else "CLAVE_FISCAL_INCORRECTA",
                "cuit": cuit,
                "error": err_str[:300],
                "mensaje": (
                    f"ARCA rechazó la Clave Fiscal para el CUIT {cuit}. "
                    "Frenamos nuevos reintentos automáticos para evitar bloqueos. "
                    "Actualizá tu Clave Fiscal correcta en el chat (`vincular_cuenta_en_chat`) o en https://impuesto.com.ar/vincular."
                ),
            }
        elif cat == "login_no_confirmado":
            _mark_login_no_confirmado(cuit, clave, err_str, actor_email=actor_email)
            err_obj = {
                "ok": False,
                "estado": "LOGIN_NO_CONFIRMADO",
                "cuit": cuit,
                "error": err_str[:300],
                "mensaje": (
                    f"ARCA recibió el login del CUIT {cuit} pero no confirmó el ingreso al portal a tiempo "
                    "(lentitud o pantalla intermedia). Reintentá en unos minutos."
                ),
            }
        else:
            err_obj = {
                "ok": False,
                "estado": "ARCA_TEMPORALMENTE_NO_DISPONIBLE",
                "cuit": cuit,
                "error": err_str[:300],
                "mensaje": (
                    f"ARCA no respondió a tiempo al consultar el CUIT {cuit} (puede estar lento o en mantenimiento). "
                    "Reintentá en unos minutos o pasá `forzar_refresco=true`."
                ),
            }
        with _audit_lock:
            entry["result"] = err_obj
            entry["finished_at"] = now
            AUDIT_CACHE[cuit] = {"ts": now, "is_error": True, "data": err_obj}
            if AUDIT_INFLIGHT.get(cuit) is entry:
                AUDIT_INFLIGHT.pop(cuit, None)
    finally:
        if got_sem:
            PLAYWRIGHT_SEM.release()
        if got_cuit:
            cuit_lk.release()
        entry["event"].set()


def _precalentar_auditoria_en_background(cuit: str, clave: str, actor_email: str = "", origen_llm: str = "prewarm") -> None:
    """Dispara la Auditoría 360° en segundo plano apenas se vincula un CUIT para que la primera consulta responda en <1s."""
    if os.environ.get("DISABLE_AUDIT_PREWARM", "").strip() == "1":
        return
    if not cuit or not clave or cuit.startswith("20333333") or cuit.startswith("20444444") or cuit.startswith("20999999"):
        return
    if _check_bad_creds(cuit, clave):
        return
    now = time.time()
    clave_hash = _hash_clave(cuit, clave)
    with _audit_lock:
        if cuit in AUDIT_INFLIGHT:
            return
        cached = AUDIT_CACHE.get(cuit)
        if cached and (now - cached["ts"]) < AUDIT_TTL_SEC:
            return
        inflight = {"started_at": now, "event": threading.Event(), "result": None, "actor_email": actor_email, "clave_hash": clave_hash}
        AUDIT_INFLIGHT[cuit] = inflight
        executor.submit(_run_auditoria_background, cuit, clave, inflight, actor_email, origen_llm, clave_hash)


def _ejecutar_auditoria_sin_timeout(
    cuit: str,
    clave: str,
    forzar_refresco: bool = False,
    actor_email: str = "",
    origen_llm: str = "mcp",
) -> Dict[str, Any]:
    """Ejecuta la auditoría 360° con caché de 15 min y espera máx. de 5s para evitar timeouts en Gemini Online / Cloudflare."""
    cb_err = _check_bad_creds(cuit, clave)
    if cb_err:
        return cb_err
    now = time.time()
    clave_hash = _hash_clave(cuit, clave)
    with _audit_lock:
        cached = AUDIT_CACHE.get(cuit)
        ttl_eff = ERROR_TTL_SEC if (cached and cached.get("is_error")) else AUDIT_TTL_SEC
        if not forzar_refresco and cached and (now - cached["ts"]) < ttl_eff:
            out = dict(cached["data"])
            out["desde_cache"] = True
            out["antiguedad_seg"] = int(now - cached["ts"])
            return out

        inflight = AUDIT_INFLIGHT.get(cuit)
        if inflight is not None and (now - inflight["started_at"]) > INFLIGHT_MAX_AGE_SEC:
            logger.warning(f"Watchdog: evicting stale AUDIT_INFLIGHT for {cuit} ({int(now - inflight['started_at'])}s)")
            AUDIT_INFLIGHT.pop(cuit, None)
            inflight = None
        if inflight is None:
            inflight = {
                "started_at": now,
                "event": threading.Event(),
                "result": None,
                "actor_email": actor_email,
                "clave_hash": clave_hash,
            }
            AUDIT_INFLIGHT[cuit] = inflight
            executor.submit(_run_auditoria_background, cuit, clave, inflight, actor_email, origen_llm, clave_hash)

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
    clave: str = "",
    clave_hash: str = "",
) -> Dict[str, Any]:
    """Ejecuta cualquier scraper ARCA en segundo plano con caché de 15 min y espera máx. 5s para evitar cuelgues en Gemini Online."""
    effective_clave_hash = clave_hash or (_hash_clave(cuit, clave) if clave else "")
    if clave:
        cb_err = _check_bad_creds(cuit, clave)
        if cb_err:
            return cb_err
    now = time.time()
    with _audit_lock:
        cached = TOOL_CACHE.get(cache_key)
        ttl_eff = ERROR_TTL_SEC if (cached and cached.get("is_error")) else AUDIT_TTL_SEC
        if cached and (now - cached["ts"]) < ttl_eff:
            data = cached["data"]
            if isinstance(data, dict):
                out = dict(data)
                out["desde_cache"] = True
                return out
            return {"ok": True, "desde_cache": True, "resultado": data}

        inflight = TOOL_INFLIGHT.get(cache_key)
        if inflight is not None and (now - inflight["started_at"]) > INFLIGHT_MAX_AGE_SEC:
            logger.warning(f"Watchdog: evicting stale TOOL_INFLIGHT for {cache_key} ({int(now - inflight['started_at'])}s)")
            TOOL_INFLIGHT.pop(cache_key, None)
            inflight = None
        if inflight is None:
            inflight = {
                "started_at": now,
                "event": threading.Event(),
                "result": None,
                "cuit": normalizar_cuit(cuit),
                "usa_login": bool(clave),
                "actor_email": actor_email,
                "clave_hash": effective_clave_hash,
            }
            TOOL_INFLIGHT[cache_key] = inflight

            def _worker():
                cuit_lk = _get_cuit_lock(cuit)
                got_cuit = cuit_lk.acquire(timeout=LOCK_ACQUIRE_TIMEOUT_SEC)
                got_sem = False
                try:
                    if not got_cuit:
                        raise ArcaNoDisponible(f"Timeout esperando lock del CUIT {cuit}.")
                    # P0-7 cierre total: re-chequear circuit breaker DESPUÉS de adquirir el lock
                    if clave:
                        cb_inner = _check_bad_creds(cuit, clave)
                        if cb_inner:
                            ts_cb = time.time()
                            with _audit_lock:
                                inflight["result"] = cb_inner
                                TOOL_CACHE[cache_key] = {"ts": ts_cb, "is_error": True, "data": cb_inner}
                                if TOOL_INFLIGHT.get(cache_key) is inflight:
                                    TOOL_INFLIGHT.pop(cache_key, None)
                            return
                    got_sem = PLAYWRIGHT_SEM.acquire(timeout=LOCK_ACQUIRE_TIMEOUT_SEC)
                    if not got_sem:
                        raise ArcaNoDisponible("Timeout esperando disponibilidad del motor headless ARCA.")
                    res = fn()
                    ts_done = time.time()
                    is_err_res = isinstance(res, dict) and res.get("ok") is False
                    if clave and not is_err_res:
                        if marcar_cuit_validado(
                            cuit,
                            email_actor=actor_email,
                            clave_hash=effective_clave_hash,
                            clave_fiscal=clave,
                        ):
                            _clear_bad_creds(cuit, clear_budget=True)
                    with _audit_lock:
                        inflight["result"] = res
                        TOOL_CACHE[cache_key] = {"ts": ts_done, "is_error": is_err_res, "data": res}
                        if TOOL_INFLIGHT.get(cache_key) is inflight:
                            TOOL_INFLIGHT.pop(cache_key, None)
                    if actor_email and accion_hist and not is_err_res:
                        registrar_evento_historial(actor_email, cuit, origen_llm, accion_hist, f"{label} (CUIT {cuit})")
                except Exception as e:
                    logger.exception(f"Error en {cache_key}")
                    ts_err = time.time()
                    err_str = str(e)
                    cat = _clasificar_error_arca(e, err_str, cuit, actor_email) if clave else "arca_no_disponible"
                    if cat == "clave_incorrecta" and clave:
                        cambio_clave = isinstance(e, ClaveIncorrecta) and bool(e.cambio_clave)
                        bloqueada = (isinstance(e, ClaveIncorrecta) and bool(e.bloqueada)) or ("BLOQUEADA" in err_str.upper())
                        _mark_bad_creds(cuit, clave, err_str, cambio_clave=cambio_clave)
                        err_obj = {
                            "ok": False,
                            "estado": "CLAVE_FISCAL_BLOQUEADA" if bloqueada else "CLAVE_FISCAL_INCORRECTA",
                            "cuit": cuit,
                            "modulo": label,
                            "error": err_str[:300],
                            "mensaje": f"ARCA rechazó la Clave Fiscal del CUIT {cuit}. Actualizala antes de reintentar para evitar bloqueos.",
                        }
                    elif cat == "login_no_confirmado" and clave:
                        _mark_login_no_confirmado(cuit, clave, err_str, actor_email=actor_email)
                        err_obj = {
                            "ok": False,
                            "estado": "LOGIN_NO_CONFIRMADO",
                            "cuit": cuit,
                            "modulo": label,
                            "error": err_str[:300],
                            "mensaje": f"ARCA recibió el login en {label} pero no confirmó el ingreso al portal a tiempo. Reintentá en unos minutos.",
                        }
                    else:
                        err_obj = {
                            "ok": False,
                            "estado": "ARCA_TEMPORALMENTE_NO_DISPONIBLE",
                            "cuit": cuit,
                            "modulo": label,
                            "error": err_str[:300],
                            "mensaje": f"ARCA no respondió a tiempo en {label} (posible lentitud o mantenimiento). Reintentá en 1 minuto.",
                        }
                    with _audit_lock:
                        inflight["result"] = err_obj
                        TOOL_CACHE[cache_key] = {"ts": ts_err, "is_error": True, "data": err_obj}
                        if TOOL_INFLIGHT.get(cache_key) is inflight:
                            TOOL_INFLIGHT.pop(cache_key, None)
                finally:
                    if got_sem:
                        PLAYWRIGHT_SEM.release()
                    if got_cuit:
                        cuit_lk.release()
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
        "version": "3.3.0",
        "mode": "headless_vault_multitenant",
        "vault_key_fingerprint": obtener_huella_vault_key(),
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
    if (data.url_conector_universal) {{
      const list = document.getElementById('urlList');
      list.innerHTML = '';
      const u = data.url_conector_universal;
      const row = document.createElement('div');
      row.className = 'url-row';
      row.innerHTML = '<span style="overflow:hidden;text-overflow:ellipsis"><strong>CONECTOR UNIVERSAL (Gemini · Claude · ChatGPT · Copilot · Cursor):</strong><br>' + u + '</span>' +
        '<button type="button" class="copy">Copiar</button>';
      row.querySelector('button').onclick = () => {{ navigator.clipboard.writeText(u); row.querySelector('button').textContent = '¡Copiado!'; }};
      list.appendChild(row);
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
def api_vincular(
    req: VincularRequest,
    x_bot_secret: Optional[str] = Header(default=None),
    x_user_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
):
    _check_secret(x_bot_secret)
    email = normalizar_email(req.email or "")
    actor_email = resolver_email_por_token(_extract_user_token(x_user_token, authorization))
    es_verificado = bool(actor_email and email and actor_email == email)

    # P0-1 & P0-2 cierre total: VERIFICAR identidad PRIMERO antes de guardar credenciales o emitir tokens
    if not email or "@" not in email:
        return {"ok": False, "acceso_denegado": True, "error": "Indicá un email válido para vincular tu cuenta."}
    if not es_verificado:
        return {
            "ok": False,
            "requiere_otp": True,
            "acceso_denegado": True,
            "error": (
                "Para vincular un CUIT o generar un token primero verificá tu email con un código de 6 dígitos "
                "(`solicitar_codigo_acceso_email` + `verificar_codigo_acceso_email`) e incluí tu `token_sesion`."
            ),
        }

    res: Dict[str, Any] = {"ok": True}
    if req.modo != "solo_token_llm":
        cuit_req = normalizar_cuit(req.cuit or "")
        owner_ya_validado = es_owner_validado(email, cuit_req)
        if not owner_ya_validado:
            if _hay_login_en_curso(cuit_req):
                return {
                    "ok": False,
                    "estado": "VALIDACION_EN_CURSO",
                    "en_validacion": True,
                    "cuit": cuit_req,
                    "error": f"VALIDACION_EN_CURSO: Ya hay un login en curso en ARCA para el CUIT {cuit_req}. Reintentá en 2 minutos.",
                }
            budget_err = _check_cuit_fail_budget(cuit_req)
            if budget_err:
                return budget_err
        res = guardar_credenciales_cifradas(
            cuit=req.cuit or "",
            clave_fiscal=req.clave_fiscal,
            modo=req.modo,
            cert_pem=req.cert_pem,
            key_pem=req.key_pem,
            alias=req.alias,
            owner_email=email,
        )
        if not res.get("ok"):
            return res
        # N1-b: invalidar caché siempre al guardar clave nueva; solo limpiar _BAD_CREDS_CB si es owner validado
        if res.get("cuit"):
            if owner_ya_validado:
                _clear_bad_creds(res["cuit"], clear_budget=False)
            else:
                _invalidar_cache_cuit(res["cuit"])

    tok = crear_token_usuario(
        email=email,
        label=req.etiqueta_token or "principal",
        custom_token=req.token_personalizado or None,
        verificado=True,
    )
    if not tok.get("ok"):
        return tok
    t = tok["token"]
    res["email"] = email
    res["token_id"] = tok["token_id"]
    res["token"] = t
    res["url_conector_universal"] = f"https://conectar.impuesto.com.ar/?token={t}"
    res["urls_privadas_mcp"] = {
        "conectar": f"https://conectar.impuesto.com.ar/?token={t}",
        "gemini": f"https://conectar.impuesto.com.ar/?token={t}",
        "claude": f"https://conectar.impuesto.com.ar/?token={t}",
        "chatgpt": f"https://conectar.impuesto.com.ar/?token={t}",
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
        if req.clave_fiscal:
            _precalentar_auditoria_en_background(res["cuit"], req.clave_fiscal, actor_email=email, origen_llm="prewarm_web")

    return res


@app.get("/api/v1/vincular/{cuit}")
def api_estado_vincular(
    cuit: str,
    x_bot_secret: Optional[str] = Header(default=None),
    x_user_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
):
    _check_secret(x_bot_secret)
    actor_email = resolver_email_por_token(_extract_user_token(x_user_token, authorization))
    if not actor_email:
        raise HTTPException(status_code=401, detail="Autenticación requerida para consultar estado de vinculación")
    ok_perm, _, reason = verificar_permiso_cuit(actor_email, cuit, nivel="lectura")
    if not ok_perm and not es_admin_plataforma(actor_email):
        raise HTTPException(status_code=403, detail=reason)
    return estado_vinculacion(cuit)


@app.delete("/api/v1/vincular/{cuit}")
def api_revocar_vincular(
    cuit: str,
    x_bot_secret: Optional[str] = Header(default=None),
    x_user_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
):
    _check_secret(x_bot_secret)
    actor_email = resolver_email_por_token(_extract_user_token(x_user_token, authorization))
    if not actor_email:
        raise HTTPException(status_code=401, detail="Autenticación requerida para revocar credenciales")
    ok_perm, role_del, reason = verificar_permiso_cuit(actor_email, cuit, nivel="lectura")
    if not (ok_perm and role_del == "owner") and not es_admin_plataforma(actor_email):
        raise HTTPException(status_code=403, detail=reason)
    _invalidar_cache_cuit(cuit)
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

    # Resolver identidad multi-tenant del usuario (header Bearer / ?token= / token_sesion en chat)
    effective_token = (x_user_token or "").strip() or str(args.get("token_sesion") or "").strip()
    actor_email = resolver_email_por_token(effective_token)
    safe_keys = [k for k in args.keys() if k not in ("clave_fiscal", "frase_clave", "frase_clave_o_token", "token_sesion")]
    logger.info(f"[MCP] tool={tool} origin={origen_llm} user={actor_email or 'ANON'} keys={safe_keys}")

    # Herramientas 100% públicas (no tocan bóveda ni datos de ningún contribuyente)
    if tool == "verificar_estado_servidores_arca_ws":
        from .arca_ws import verificar_estado_servidores_wsfe
        return verificar_estado_servidores_wsfe(ambiente=args.get("ambiente", "produccion"))

    if tool == "verificar_proveedor_apocrifo_apoc":
        from .scraper_extras_arca import verificar_proveedor_apocrifo_apoc
        cuit_prov = normalizar_cuit(args.get("cuit_proveedor", ""))
        return _run_tool_sin_timeout(
            f"eapoc:{cuit_prov}", "Base e-APOC ARCA",
            lambda: verificar_proveedor_apocrifo_apoc(cuit_prov),
            cuit=cuit_prov or "publico", actor_email=actor_email or "", origen_llm=origen_llm,
        )

    # =========================================================================
    # AUTENTICACIÓN Y VINCULACIÓN 100% DENTRO DEL CHAT (CERO SALIR DEL LLM)
    # =========================================================================
    if tool == "vincular_cuenta_en_chat":
        em = normalizar_email(args.get("email", ""))
        cuit_in = normalizar_cuit(args.get("cuit", ""))
        clave_in = (args.get("clave_fiscal") or "").strip()
        frase_in = (args.get("frase_clave") or "").strip()
        modo_in = (args.get("modo") or "solo_lectura_cifrada").strip()

        if "@" not in em:
            return {"ok": False, "error": "Indicá un email válido para quedar registrado como Owner de tu cuenta."}
        if len(cuit_in) != 11 or not clave_in:
            return {"ok": False, "error": "Indicá tu CUIT (11 dígitos) y tu Clave Fiscal ARCA para vincular en modo solo lectura."}

        es_verificado_chat = bool(actor_email and actor_email == em)
        tok = crear_token_usuario(
            email=em,
            label=f"chat_{origen_llm}",
            custom_token=frase_in or None,
            verificado=es_verificado_chat,
        )
        if not tok.get("ok"):
            return tok

        owner_ya_validado_chat = es_owner_validado(em, cuit_in)
        if not owner_ya_validado_chat:
            if _hay_login_en_curso(cuit_in):
                return {
                    "ok": False,
                    "estado": "VALIDACION_EN_CURSO",
                    "en_validacion": True,
                    "cuit": cuit_in,
                    "error": f"VALIDACION_EN_CURSO: Ya hay un login en curso en ARCA para el CUIT {cuit_in}. Reintentá en 2 minutos.",
                }
            budget_err = _check_cuit_fail_budget(cuit_in)
            if budget_err:
                return budget_err
        res_v = guardar_credenciales_cifradas(
            cuit=cuit_in,
            clave_fiscal=clave_in,
            modo=modo_in,
            owner_email=em,
        )
        if not res_v.get("ok"):
            return res_v
        if owner_ya_validado_chat:
            _clear_bad_creds(cuit_in, clear_budget=False)
        else:
            _invalidar_cache_cuit(cuit_in)

        registrar_evento_historial(
            email=em,
            cuit=cuit_in,
            origen_llm=origen_llm,
            accion="vincular_en_chat",
            titulo=f"CUIT {cuit_in} vinculado 100% en chat ({origen_llm})",
            detalle=f"Owner: {em} · Modo: {modo_in}",
        )
        _precalentar_auditoria_en_background(cuit_in, clave_in, actor_email=em, origen_llm=f"prewarm_{origen_llm}")
        return {
            "ok": True,
            "usuario": em,
            "cuit": cuit_in,
            "es_owner_plataforma": es_admin_plataforma(em),
            "token_sesion": tok["token"],
            "mensaje": (
                f"¡Listo! Tu CUIT {cuit_in} quedó cifrado en modo solo lectura bajo tu cuenta {em}. "
                "Ya podés operar todo desde este mismo chat sin salir a ninguna web."
            ),
            "instruccion_para_ia": (
                "Guardá `token_sesion` en el contexto de esta conversación y pasalo en el parámetro `token_sesion` "
                "en todas las herramientas que llames a partir de ahora en este chat (NO repitas la Clave Fiscal en tu respuesta). "
                "Confirmale al usuario en 2 líneas que ya está vinculado y arrancá directo con lo que necesite."
            ),
        }

    if tool == "solicitar_codigo_acceso_email":
        return solicitar_codigo_otp_email(email=args.get("email", ""), client_ip=_extract_client_ip(request))

    if tool == "verificar_codigo_acceso_email":
        return verificar_codigo_otp_email(
            email=args.get("email", ""),
            codigo=args.get("codigo", ""),
            origen_llm=origen_llm,
            client_ip=_extract_client_ip(request),
        )

    if tool == "iniciar_sesion_en_chat":
        from .limite_login import LIMITE_LOGIN_CHAT
        em = normalizar_email(args.get("email", ""))
        client_ip = _extract_client_ip(request)
        key_u = em or "anon"
        ok_lim, msg_lim = LIMITE_LOGIN_CHAT.chequear(client_ip, key_u)
        if not ok_lim:
            return {"ok": False, "acceso_denegado": True, "rate_limited": True, "error": msg_lim}
        secreto = (args.get("frase_clave_o_token") or args.get("frase_clave") or args.get("token_sesion") or "").strip()
        resolved = resolver_email_por_token(secreto)
        if not resolved or (em and resolved != em):
            LIMITE_LOGIN_CHAT.registrar_fallo(client_ip, key_u)
            return {
                "ok": False,
                "acceso_denegado": True,
                "error": "Email o frase clave/token incorrectos. Verificá tu frase clave o pedí un código de 6 dígitos (`solicitar_codigo_acceso_email`).",
            }
        LIMITE_LOGIN_CHAT.registrar_exito(client_ip, resolved)
        cuits = listar_cuits_autorizados(resolved)
        return {
            "ok": True,
            "usuario": resolved,
            "es_owner_plataforma": es_admin_plataforma(resolved),
            "token_sesion": secreto,
            "empresas_vinculadas": cuits,
            "mensaje": f"Sesión iniciada correctamente como {resolved} ({len(cuits)} CUIT(s) autorizados).",
            "instruccion_para_ia": (
                "Pasá este `token_sesion` en el parámetro `token_sesion` de todas las herramientas que llames en este chat. "
                "NO muestres la frase clave ni el token en tu respuesta al usuario. Saludalo y avanzá directo."
            ),
        }

    # =========================================================================
    # BARRERA ESTRICTA MULTI-TENANT: a partir de acá EXIGE token válido
    # =========================================================================
    if not actor_email:
        return _auth_required_error(public_base)

    if esta_usuario_suspendido(actor_email):
        return {
            "ok": False,
            "acceso_denegado": True,
            "cuenta_suspendida": True,
            "usuario": actor_email,
            "mensaje": "Tu cuenta en impuesto.com.ar se encuentra suspendida temporalmente. Contactá a soporte para reactivarla.",
        }

    if esta_en_mantenimiento() and not es_admin_plataforma(actor_email):
        an = obtener_anuncio_global_activo()
        return {
            "ok": False,
            "modo_mantenimiento": True,
            "mensaje": (an or {}).get("mensaje") or "impuesto.com.ar está realizando un mantenimiento programado de pocos minutos. Tus datos están seguros; volvé a intentar en breve.",
        }

    # =========================================================================
    # BACKOFFICE DE PLATAFORMA (SUPER-ADMIN OWNER · SOLO PLATFORM_ADMIN_EMAILS)
    # =========================================================================
    if tool == "admin_tablero_plataforma":
        out = admin_resumen_plataforma(actor_email)
        if out.get("ok"):
            with _audit_lock:
                out["runtime_oracle"] = {
                    "version": "3.1.0",
                    "cached_audits": len(AUDIT_CACHE),
                    "inflight_audits": len(AUDIT_INFLIGHT),
                    "cached_tools": len(TOOL_CACHE),
                    "inflight_tools": len(TOOL_INFLIGHT),
                }
        return out

    if tool == "admin_listar_clientes_plataforma":
        return admin_listar_clientes(
            admin_email=actor_email,
            filtro=args.get("filtro", ""),
            plan=args.get("plan", ""),
            limite=int(args.get("limite", 50)),
        )

    if tool == "admin_ver_movimientos_plataforma":
        return admin_ver_movimientos(
            admin_email=actor_email,
            email=args.get("email", ""),
            cuit=args.get("cuit", ""),
            origen_llm=args.get("origen_llm", ""),
            limite=int(args.get("limite", 50)),
        )

    if tool == "admin_gestionar_suscripcion_cliente":
        return admin_gestionar_suscripcion(
            admin_email=actor_email,
            target_email=args.get("email", ""),
            plan=args.get("plan", "pro"),
            estado_cuenta=args.get("estado_cuenta", "activo"),
            precio_mensual_ars=float(args.get("precio_mensual_ars", 0.0)),
            nota=args.get("nota", ""),
        )

    if tool == "admin_accion_emergencia_plataforma":
        if not es_admin_plataforma(actor_email):
            return {"ok": False, "acceso_denegado": True, "error": "Acción restringida al Super-Admin Owner de impuesto.com.ar."}
        accion = (args.get("accion") or "").strip().lower()
        objetivo = (args.get("objetivo") or "").strip()
        if accion == "limpiar_cache_auditorias":
            with _audit_lock:
                if objetivo:
                    c = normalizar_cuit(objetivo)
                    AUDIT_CACHE.pop(c, None)
                    for k in [k for k in TOOL_CACHE if c in k]:
                        TOOL_CACHE.pop(k, None)
                    return {"ok": True, "accion": accion, "objetivo": c, "mensaje": f"Caché limpiada para CUIT {c}."}
                n_a, n_t = len(AUDIT_CACHE), len(TOOL_CACHE)
                AUDIT_CACHE.clear()
                TOOL_CACHE.clear()
                return {"ok": True, "accion": accion, "auditorias_limpiadas": n_a, "tools_limpiados": n_t}
        if accion == "revocar_tokens_usuario":
            return revocar_tokens_usuario(objetivo)
        if accion == "suspender_usuario":
            return admin_gestionar_suscripcion(actor_email, objetivo, plan="free", estado_cuenta="suspendido", nota="Suspendido desde Backoffice LLM")
        if accion == "reactivar_usuario":
            return admin_gestionar_suscripcion(actor_email, objetivo, plan="pro", estado_cuenta="activo", nota="Reactivado desde Backoffice LLM")
        if accion == "resumen_salud_sistema":
            with _audit_lock:
                return {
                    "ok": True,
                    "version": "3.1.0",
                    "cached_audits": len(AUDIT_CACHE),
                    "inflight_audits": len(AUDIT_INFLIGHT),
                    "cached_tools": len(TOOL_CACHE),
                    "inflight_tools": len(TOOL_INFLIGHT),
                    "active_jobs": len(jobs),
                }
        return {"ok": False, "error": f"Acción '{accion}' desconocida. Usá: limpiar_cache_auditorias, revocar_tokens_usuario, suspender_usuario, reactivar_usuario, resumen_salud_sistema."}

    if tool == "admin_metricas_growth_saas":
        return admin_metricas_growth_saas(
            admin_email=actor_email,
            tipo_cambio_usd=float(args.get("tipo_cambio_usd", 1200.0)),
        )

    if tool == "admin_detectar_oportunidades_y_riesgo":
        return admin_detectar_oportunidades_y_riesgo(
            admin_email=actor_email,
            dias_inactividad_churn=int(args.get("dias_inactividad_churn", 14)),
        )

    if tool == "admin_gestionar_feature_flags_y_limites":
        return admin_gestionar_feature_flags_y_limites(
            admin_email=actor_email,
            accion=args.get("accion", "listar"),
            flag_nombre=args.get("flag_nombre", ""),
            flag_valor=args.get("flag_valor"),
            plan_nombre=args.get("plan_nombre", ""),
            plan_limites=args.get("plan_limites"),
        )

    if tool == "admin_gestionar_cupones_y_referidos":
        return admin_gestionar_cupones_y_referidos(
            admin_email=actor_email,
            accion=args.get("accion", "listar"),
            codigo=args.get("codigo", ""),
            descuento_pct=int(args.get("descuento_pct", 0)),
            meses_gratis=int(args.get("meses_gratis", 0)),
            plan_objetivo=args.get("plan_objetivo", "todos"),
            usos_maximos=int(args.get("usos_maximos", 100)),
            referidor_email=args.get("referidor_email", ""),
        )

    if tool == "admin_gestionar_soporte_y_anuncios":
        return admin_gestionar_soporte_y_anuncios(
            admin_email=actor_email,
            accion=args.get("accion", "listar_tickets"),
            cliente_email=args.get("cliente_email", ""),
            asunto=args.get("asunto", ""),
            detalle=args.get("detalle", ""),
            prioridad=args.get("prioridad", "media"),
            ticket_id=args.get("ticket_id", ""),
            anuncio_activo=args.get("anuncio_activo"),
            anuncio_titulo=args.get("anuncio_titulo", ""),
            anuncio_mensaje=args.get("anuncio_mensaje", ""),
        )

    if tool == "admin_exportar_reporte_inversor_markdown":
        return admin_exportar_reporte_inversor_markdown(
            admin_email=actor_email,
            tipo_cambio_usd=float(args.get("tipo_cambio_usd", 1200.0)),
        )

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
            "es_owner_plataforma": es_admin_plataforma(actor_email),
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

    # Determinar nivel de permiso requerido (escritura solo si confirmado===True estricto en acciones mutantes — P0-5)
    confirmado_strict = _parse_bool_strict(args.get("confirmado", False))
    es_escritura = (tool in ("emitir_factura_wsfe", "consultar_y_renovar_certificado_mipyme") and confirmado_strict)
    nivel_req = "escritura" if es_escritura else "lectura"

    cuit, clave, err = _resolve_creds_authorized(actor_email, args, public_base, nivel=nivel_req)
    if err:
        return err

    if tool == "auditar_estado_integral_arca":
        forzar_req = _parse_bool_strict(args.get("forzar_refresco", False))
        if forzar_req and not es_owner_validado(actor_email, cuit):
            ok_ref, retry_sec = verificar_y_marcar_refresco_no_validado(cuit, cooldown_seg=600.0)
            if not ok_ref:
                return {
                    "ok": False,
                    "rate_limited": True,
                    "cuit": cuit,
                    "reintentar_en_seg": retry_sec,
                    "error": "Límite de reintentos con forzar_refresco en CUIT pendiente de validación (máx. 1 cada 10 min).",
                }
        return _ejecutar_auditoria_sin_timeout(
            cuit=cuit,
            clave=clave,
            forzar_refresco=forzar_req,
            actor_email=actor_email,
            origen_llm=origen_llm,
        )

    if tool == "consultar_ccma_cuenta_corriente":
        audit_inflight_active = False
        with _audit_lock:
            cached = AUDIT_CACHE.get(cuit)
            if cached and not cached.get("is_error") and (time.time() - cached["ts"]) < AUDIT_TTL_SEC:
                ccma = (cached["data"] or {}).get("ccma")
                if ccma and not ccma.get("error"):
                    return {"ok": True, "cuit": cuit, "desde_cache": True, "ccma": ccma}
            audit_inflight_active = cuit in AUDIT_INFLIGHT
        if audit_inflight_active:
            return _ejecutar_auditoria_sin_timeout(cuit=cuit, clave=clave, actor_email=actor_email, origen_llm=origen_llm)
        from .auditoria_unificada import consultar_ccma_preciso
        return _run_tool_sin_timeout(
            f"ccma:{cuit}", "CCMA (Monotributo y Autónomos)",
            lambda: consultar_ccma_preciso(cuit=cuit, clave=clave),
            cuit=cuit, actor_email=actor_email, origen_llm=origen_llm, accion_hist="consulta_ccma", clave=clave,
        )

    if tool == "consultar_bienes_personales_web":
        from .scraper_bbpp import consultar_bienes_personales_web
        return _run_tool_sin_timeout(
            f"bbpp:{cuit}", "Bienes Personales Web (F. 762)",
            lambda: consultar_bienes_personales_web(usuario=cuit, clave=clave),
            cuit=cuit, actor_email=actor_email, origen_llm=origen_llm, accion_hist="consulta_bbpp", clave=clave,
        )

    if tool == "consultar_nuestra_parte_arca":
        from .scraper_extras_arca import consultar_nuestra_parte
        return _run_tool_sin_timeout(
            f"nuestraparte:{cuit}", "Nuestra Parte ARCA",
            lambda: consultar_nuestra_parte(usuario=cuit, clave=clave),
            cuit=cuit, actor_email=actor_email, origen_llm=origen_llm, accion_hist="consulta_nuestra_parte", clave=clave,
        )

    if tool == "consultar_mis_retenciones_arca":
        from .scraper_extras_arca import consultar_mis_retenciones
        obj = args.get("cuit_objetivo") or cuit
        return _run_tool_sin_timeout(
            f"retenciones:{cuit}:{obj}", "Mis Retenciones ARCA",
            lambda: consultar_mis_retenciones(usuario=cuit, clave=clave, cuit_objetivo=args.get("cuit_objetivo")),
            cuit=cuit, actor_email=actor_email, origen_llm=origen_llm, accion_hist="consulta_retenciones", clave=clave,
        )

    if tool == "consultar_y_renovar_certificado_mipyme":
        from .scraper_extras_arca import consultar_y_renovar_certificado_mipyme
        emp = args.get("cuit_empresa", cuit)
        conf = confirmado_strict
        return _run_tool_sin_timeout(
            f"mipyme:{cuit}:{emp}:{conf}", "Certificado MiPyME (F. 1272)",
            lambda: consultar_y_renovar_certificado_mipyme(usuario=cuit, clave=clave, cuit_empresa=emp, confirmado=conf),
            cuit=cuit, actor_email=actor_email, origen_llm=origen_llm, accion_hist="consulta_mipyme", clave=clave,
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
            cuit=cuit, actor_email=actor_email, origen_llm=origen_llm, accion_hist="consulta_comprobantes", clave=clave,
        )

    if tool == "leer_notificaciones_dfe":
        from .scraper import consultar_notificaciones_dfe
        obj = args.get("cuit") or cuit
        return _run_tool_sin_timeout(
            f"dfe:{cuit}:{obj}", "Domicilio Fiscal Electrónico (DFE)",
            lambda: {"ok": True, "cuit": obj, "notificaciones": consultar_notificaciones_dfe(usuario=cuit, clave=clave, cuit_objetivo=args.get("cuit"))},
            cuit=cuit, actor_email=actor_email, origen_llm=origen_llm, accion_hist="consulta_dfe", clave=clave,
        )

    if tool in ("consultar_estado_monotributo", "consultar_situacion_monotributo"):
        with _audit_lock:
            cached = AUDIT_CACHE.get(cuit)
            if cached and not cached.get("is_error") and (time.time() - cached["ts"]) < AUDIT_TTL_SEC:
                mono = (cached["data"] or {}).get("portal_monotributo")
                if mono and not mono.get("error"):
                    return {"ok": True, "cuit": cuit, "desde_cache": True, "portal_monotributo": mono}
        return _ejecutar_auditoria_sin_timeout(cuit=cuit, clave=clave, actor_email=actor_email, origen_llm=origen_llm)

    if tool == "consultar_padron_cuit_ws":
        from .arca_ws import consultar_padron_a5
        return consultar_padron_a5(cuit_consulta=args.get("cuit_consulta", cuit), cuit_representado=cuit, ambiente=args.get("ambiente", "produccion"))

    if tool == "emitir_factura_wsfe":
        from .arca_ws import emitir_comprobante_wsfe
        from .wsfe_idempotencia import emitir_wsfe_con_idempotencia
        cuit_emisor_req = normalizar_cuit(args.get("cuit_emisor", "") or cuit)
        if cuit_emisor_req != cuit:
            return {
                "ok": False,
                "acceso_denegado": True,
                "error": f"El CUIT emisor ({cuit_emisor_req}) no coincide con el CUIT autorizado ({cuit}). Operación bloqueada por seguridad.",
            }
        pto_vta_in = int(args.get("pto_vta", 1))
        cbte_tipo_in = int(args.get("cbte_tipo", 11))
        ambiente_in = (args.get("ambiente") or "homologacion").strip().lower()
        idem_key = str(args.get("idempotency_key") or "").strip()
        reemitir_dup = _parse_bool_strict(args.get("reemitir_aunque_duplicado"))

        if confirmado_strict:
            wsfe_lk = _get_wsfe_lock(cuit, pto_vta_in, cbte_tipo_in)

            def _registrar_emision(res_ok: Dict[str, Any], fue_override: bool) -> None:
                suf = " [OVERRIDE reemitir_aunque_duplicado=true]" if fue_override else ""
                if res_ok.get("adoptado"):
                    suf += " [CAE ADOPTADO]"
                if res_ok.get("reemitido_tras_no_emitido_confirmado"):
                    suf += " [REEMITIDO TRAS NO_EMITIDO_CONFIRMADO]"
                registrar_evento_historial(
                    actor_email,
                    cuit,
                    origen_llm,
                    "emitir_factura_wsfe",
                    f"Factura WSFE #{res_ok.get('cbte_nro', '?')} CAE {res_ok.get('cae', '')} a {args.get('receptor_cuit', '')} por ${args.get('importe_neto', 0)}{suf}",
                )

            return emitir_wsfe_con_idempotencia(
                cuit_emisor=cuit,
                pto_vta=pto_vta_in,
                cbte_tipo=cbte_tipo_in,
                receptor_cuit=args.get("receptor_cuit", ""),
                importe_neto=float(args.get("importe_neto", 0)),
                importe_iva=float(args.get("importe_iva", 0)),
                concepto=int(args.get("concepto", 2)),
                ambiente=ambiente_in,
                cbte_asoc=args.get("cbte_asoc"),
                condicion_iva_receptor_id=args.get("condicion_iva_receptor_id"),
                idempotency_key=idem_key,
                reemitir_aunque_duplicado=reemitir_dup,
                wsfe_lock=wsfe_lk,
                on_emit_ok=_registrar_emision,
            )

        return emitir_comprobante_wsfe(
            cuit_emisor=cuit,
            pto_vta=pto_vta_in,
            cbte_tipo=cbte_tipo_in,
            receptor_cuit=args.get("receptor_cuit", ""),
            importe_neto=float(args.get("importe_neto", 0)),
            importe_iva=float(args.get("importe_iva", 0)),
            concepto=int(args.get("concepto", 2)),
            ambiente=ambiente_in,
            confirmado=False,
            cbte_asoc=args.get("cbte_asoc"),
            condicion_iva_receptor_id=args.get("condicion_iva_receptor_id"),
        )

    if tool == "resolver_emision_incierta":
        from .wsfe_idempotencia import resolver_emision_incierta
        cuit_req = normalizar_cuit(args.get("cuit") or args.get("cuit_emisor") or cuit)
        ok_own, _, reason_own = verificar_permiso_cuit(actor_email, cuit_req, nivel="owner")
        if not ok_own:
            return {"ok": False, "acceso_denegado": True, "error": reason_own}
        res_man = resolver_emision_incierta(
            cuit_emisor=cuit_req,
            huella=str(args.get("huella") or ""),
            accion=str(args.get("accion") or ""),
            cbte_nro=int(args["cbte_nro"]) if args.get("cbte_nro") else None,
            ambiente=args.get("ambiente"),
            confirmado=confirmado_strict,
            forzar=_parse_bool_strict(args.get("forzar", False)),
        )
        if res_man.get("ok"):
            registrar_evento_historial(
                actor_email,
                cuit_req,
                origen_llm,
                "resolver_emision_incierta",
                f"Resolución manual ({args.get('accion')}) huella={str(args.get('huella',''))[:16]} -> {res_man.get('estado') or res_man.get('cae')}",
            )
        return res_man

    if tool == "generar_certificado_csr_arca":
        from .arca_ws import generar_csr_arca
        return generar_csr_arca(cuit=args.get("cuit", cuit), razon_social=args.get("razon_social", "Contribuyente"), alias=args.get("alias", "impuesto_mcp"))

    return {"ok": False, "error": f"Herramienta '{tool}' no mapeada aún en el backend headless."}


def run_job(job_id: str, params: AutomationParams):
    jobs[job_id]["status"] = "in_process"
    try:
        with PLAYWRIGHT_SEM:
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
        jobs[job_id]["message"] = str(e)[:300]


@app.post("/api/v1/automations")
def start_automation(req: StartRequest, x_bot_secret: Optional[str] = Header(default=None)):
    _check_secret(x_bot_secret)
    if req.automation != "mis-comprobantes":
        raise HTTPException(status_code=400, detail="Automatización desconocida")
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"id": job_id, "status": "in_process", "created_at": time.time(), "data": [], "message": ""}
    executor.submit(run_job, job_id, req.params)
    return {"id": job_id, "status": "in_process"}


@app.get("/api/v1/automations/{job_id}")
def get_automation_status(job_id: str, x_bot_secret: Optional[str] = Header(default=None)):
    _check_secret(x_bot_secret)
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
