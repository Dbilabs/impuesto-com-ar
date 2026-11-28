"""
bot/wsfe_idempotencia.py
Idempotencia persistente y adopción del CAE para emisión WSFEv1 (Fase 3.1 / N4).

Diseño (inspirado en colaEmision.js / syncEmitidos.js de Arcanum):
- Persistencia cifrada con escritura atómica en `<VAULT_DIR>/wsfe_idempotencia.enc`
  (volumen montado en producción; directorio temporal en tests). Nada en RAM como
  fuente de verdad: sobrevive reinicios de proceso.
- Huella del lado del servidor:
  sha256(ambiente|cuit_emisor|pto_vta|cbte_tipo|concepto|doc_tipo|doc_nro|imp_total:.2f|cbte_fch)
  La `idempotency_key` del LLM es opcional (se guarda y puede indexar replay, pero un
  reintento con otra key para la misma venta sigue encontrando el registro por huella).
- Máquina de estados: PENDIENTE -> AUTORIZADO | RECHAZADO | INCIERTO.
  * PENDIENTE se persiste ANTES de FECAESolicitar junto con `ultimo_nro_antes`.
  * En reintento dentro de 10 min:
    - AUTORIZADO -> devuelve el mismo CAE con `replay: True`.
    - PENDIENTE / INCIERTO -> reconcilia vía FECompUltimoAutorizado + FECompConsultar.
      Si coincide ImpTotal, DocNro y CbteFch -> adopta (`adoptado: True`).
      Si no coincide o no se puede confirmar -> `ESTADO_INCIERTO_REQUIERE_REVISION`
      y NUNCA re-emite automáticamente.
- Ventas idénticas legítimas: solo con `reemitir_aunque_duplicado=True` + `confirmado=True`.
"""

import datetime
import hashlib
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from . import arca_ws
from . import boveda_segura as bv

logger = logging.getLogger("impuesto.wsfe_idempotencia")

WSFE_IDEM_WINDOW_SEC = 600.0     # 10 minutos para replay de AUTORIZADO por huella
WSFE_IDEM_RETENTION_SEC = 86400.0  # 24 horas de retención en disco
NO_EMITIDO_GRACE_SEC = 120.0       # 2 minutos antes de confirmar NO_EMITIDO_CONFIRMADO (N4-f)
MAX_RECONCILE_SCAN = 20            # Tope de comprobantes a revisar en (ultimo_antes, ultimo_ahora]
_idem_io_lock = threading.Lock()


def _idem_store_path() -> Path:
    return bv.VAULT_DIR / "wsfe_idempotencia.enc"


def _load_store_locked() -> Dict[str, Any]:
    data = bv._read_enc_json(_idem_store_path(), {"by_huella": {}, "by_key": {}})
    if not isinstance(data, dict):
        data = {"by_huella": {}, "by_key": {}}
    data.setdefault("by_huella", {})
    data.setdefault("by_key", {})
    return data


def _save_store_locked(data: Dict[str, Any]) -> None:
    now = time.time()
    # Podar entradas >24h SOLO si están resueltas (AUTORIZADO/RECHAZADO).
    # N4-b: NUNCA borrar PENDIENTE o INCIERTO sin resolver; retener y alertar en log.
    for bucket in ("by_huella", "by_key"):
        stale = []
        for k, v in (data.get(bucket) or {}).items():
            if not isinstance(v, dict):
                continue
            age = now - float(v.get("updated_at") or v.get("created_at") or 0)
            if age <= WSFE_IDEM_RETENTION_SEC:
                continue
            if v.get("estado") in ("PENDIENTE", "INCIERTO"):
                logger.warning(
                    f"[WSFE N4] Registro {v.get('estado')} sin resolver >24h retenido "
                    f"(cuit={v.get('cuit_emisor')}, pto_vta={v.get('pto_vta')}, huella={str(v.get('huella',''))[:12]})"
                )
                continue
            stale.append(k)
        for k in stale:
            data[bucket].pop(k, None)
    bv._write_enc_json(_idem_store_path(), data)


def calcular_huella_wsfe(
    *,
    cuit_emisor: str,
    pto_vta: int,
    cbte_tipo: int,
    concepto: int,
    doc_tipo: int,
    doc_nro: int,
    imp_total: float,
    cbte_fch: str,
    ambiente: str = "homologacion",
    idempotency_key: str = "",
) -> str:
    """Calcula la huella determinística del servidor para una emisión WSFE."""
    cuit_em = bv.normalizar_cuit(cuit_emisor)
    env_k = "homologacion" if "homo" in (ambiente or "homologacion").lower() else "produccion"
    base = (
        f"{env_k}|{cuit_em}|{int(pto_vta)}|{int(cbte_tipo)}|{int(concepto)}|"
        f"{int(doc_tipo)}|{int(doc_nro)}|{round(float(imp_total), 2):.2f}|{str(cbte_fch).strip()}"
    )
    if idempotency_key:
        base = f"{base}|{idempotency_key.strip()}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _normalizar_receptor(receptor_cuit: str) -> tuple[int, int]:
    cuit_rec = "".join(c for c in str(receptor_cuit or "") if c.isdigit())
    doc_tipo = 80 if len(cuit_rec) == 11 else 99
    doc_nro = int(cuit_rec) if cuit_rec else 0
    return doc_tipo, doc_nro


def _respuesta_incierta(
    *,
    cuit_emisor: str,
    pto_vta: int,
    cbte_tipo: int,
    huella: str,
    detalle: str,
) -> Dict[str, Any]:
    return {
        "ok": False,
        "estado": "ESTADO_INCIERTO_REQUIERE_REVISION",
        "incierto": True,
        "cuit": cuit_emisor,
        "punto_venta": pto_vta,
        "cbte_tipo": cbte_tipo,
        "huella_idempotencia": huella[:16],
        "error": (
            f"Estado incierto al emitir comprobante ({detalle}). "
            "Para evitar emitir una factura duplicada NO se re-emitió automáticamente. "
            "Verificá en ARCA (Comprobantes en Línea / FECompConsultar) si el comprobante ya obtuvo CAE."
        ),
    }


def _reconciliar_registro_incierto(
    *,
    rec: Dict[str, Any],
    cuit_emisor: str,
    pto_vta: int,
    cbte_tipo: int,
    doc_nro: int,
    imp_total: float,
    cbte_fch: str,
    ambiente: str,
    now_ts: float,
) -> tuple[str, Optional[Dict[str, Any]]]:
    """Reconcilia un PENDIENTE/INCIERTO contra ARCA (FECompUltimoAutorizado + FECompConsultar).

    N4-g / N4-h / N4-i:
      - Sin `ultimo_nro_antes` -> siempre INCIERTO (resolución manual únicamente).
      - Si `ultimo_ahora < ultimo_antes` -> respuesta anómala de WSFE -> INCIERTO (nunca NO_EMITIDO).
      - Un número cuenta como revisado SOLO con un ResultGet válido (cae presente). Ante None o excepción -> INCIERTO.
      - Gracia de 2 min medida desde `intento_at` fijo (no se reinicia en cada reintento).
      - NO_EMITIDO_CONFIRMADO solo con evidencia positiva.
    """
    ultimo_antes = rec.get("ultimo_nro_antes")
    if ultimo_antes is None:
        return "INCIERTO", None
    ultimo_antes_int = int(ultimo_antes)
    # N4-i: usar intento_at fijo para no reiniciar la ventana de 2 min en cada reintento
    elapsed = now_ts - float(rec.get("intento_at") or rec.get("created_at") or now_ts)
    try:
        ultimo_ahora = arca_ws.obtener_ultimo_autorizado_wsfe(
            cuit_emisor=cuit_emisor,
            pto_vta=pto_vta,
            cbte_tipo=cbte_tipo,
            ambiente=ambiente,
        )
    except Exception as exc:
        logger.warning(f"[WSFE N4] Error consultando FECompUltimoAutorizado para reconciliar: {exc}")
        return "INCIERTO", None

    if ultimo_ahora is None:
        return "INCIERTO", None
    ultimo_ahora = int(ultimo_ahora)

    # N4-g: los números WSFE son monotónicos crecientes; ultimo_ahora < ultimo_antes indica error de WSFE
    if ultimo_ahora < ultimo_antes_int:
        logger.warning(f"[WSFE N4-g] FECompUltimoAutorizado devolvió {ultimo_ahora} < ultimo_antes={ultimo_antes_int}; se mantiene INCIERTO.")
        return "INCIERTO", None

    # Caso 1 (N4-f): evidencia positiva FECompUltimoAutorizado == ultimo_nro_antes
    if ultimo_ahora == ultimo_antes_int:
        if elapsed >= NO_EMITIDO_GRACE_SEC:
            return "NO_EMITIDO_CONFIRMADO", None
        return "INCIERTO", None

    total_nuevos = ultimo_ahora - ultimo_antes_int
    if total_nuevos <= MAX_RECONCILE_SCAN:
        desde = ultimo_antes_int + 1
        rango_completo = True
    else:
        desde = ultimo_ahora - MAX_RECONCILE_SCAN + 1
        rango_completo = False

    revisados_validos = 0
    for nro in range(ultimo_ahora, desde - 1, -1):
        try:
            comp = arca_ws.consultar_comprobante_por_nro_wsfe(
                cuit_emisor=cuit_emisor,
                pto_vta=pto_vta,
                cbte_tipo=cbte_tipo,
                cbte_nro=nro,
                ambiente=ambiente,
            )
        except Exception as exc:
            logger.warning(f"[WSFE N4] Error en FECompConsultar({nro}): {exc}")
            return "INCIERTO", None
        # N4-g: un número cuenta como revisado SOLO con ResultGet válido (cae presente). Ante None -> INCIERTO.
        if not comp or not comp.get("cae"):
            logger.warning(f"[WSFE N4-g] FECompConsultar({nro}) devolvió None o sin CAE dentro del rango autorizado; se mantiene INCIERTO.")
            return "INCIERTO", None
        revisados_validos += 1
        imp_match = abs(round(float(comp.get("imp_total", -1)), 2) - round(float(imp_total), 2)) < 0.005
        doc_match = int(comp.get("doc_nro", -1)) == int(doc_nro)
        fch_match = str(comp.get("cbte_fch", "")).strip() == str(cbte_fch).strip()
        if imp_match and doc_match and fch_match:
            return "ADOPTADO", {
                "ok": True,
                "modo": "EMISION_OFICIAL_WSFEV1",
                "ambiente": ambiente,
                "emisor_cuit": cuit_emisor,
                "punto_venta": pto_vta,
                "cbte_tipo": cbte_tipo,
                "cbte_nro": int(comp.get("cbte_nro", nro)),
                "receptor_doc_nro": int(doc_nro),
                "fecha": cbte_fch,
                "importe_total": round(float(imp_total), 2),
                "resultado": "APROBADO",
                "cae": str(comp["cae"]),
                "cae_vencimiento": str(comp.get("cae_vencimiento", "")),
                "adoptado": True,
                "replay": True,
                "idempotente_reusado": True,
                "mensaje": (
                    f"Comprobante #{nro} ya había sido autorizado por ARCA (CAE {comp['cae']}). "
                    "Se adoptó el CAE existente sin emitir un duplicado."
                ),
            }

    # Caso 3 (N4-f + N4-g): rango completo revisado con ResultGet válidos en TODOS los números y >= 2 min
    if rango_completo and revisados_validos == total_nuevos and elapsed >= NO_EMITIDO_GRACE_SEC:
        return "NO_EMITIDO_CONFIRMADO", None
    return "INCIERTO", None


def resolver_emision_incierta(
    *,
    cuit_emisor: str,
    huella: str,
    accion: str,
    cbte_nro: Optional[int] = None,
    ambiente: Optional[str] = None,
    confirmado: bool = False,
    forzar: bool = False,
) -> Dict[str, Any]:
    """Tool administrativa exclusiva del Owner validado para resolver manualmente un registro INCIERTO/PENDIENTE (N4-f / N4-j).
    Requiere confirmado=True. `accion`: 'marcar_no_emitido' | 'adoptar_nro'."""
    if not confirmado:
        return {
            "ok": False,
            "requiere_confirmacion": True,
            "error": "Para ejecutar `resolver_emision_incierta` debés confirmar explícitamente con `confirmado: true`.",
        }
    cuit_em = bv.normalizar_cuit(cuit_emisor)
    h_q = (huella or "").strip().lower()
    act = (accion or "").strip().lower()
    if act not in ("marcar_no_emitido", "adoptar_nro"):
        return {"ok": False, "error": "Acción inválida. Usá 'marcar_no_emitido' o 'adoptar_nro'."}
    if not h_q or len(h_q) < 8:
        return {"ok": False, "error": "Indicá la huella (al menos los primeros 8 caracteres) del registro incierto."}

    with _idem_io_lock:
        store = _load_store_locked()
        match_key = None
        rec = None
        for k, v in (store.get("by_huella") or {}).items():
            if not isinstance(v, dict):
                continue
            if v.get("cuit_emisor") != cuit_em:
                continue
            if k.lower() == h_q or k.lower().startswith(h_q):
                match_key = k
                rec = dict(v)
                break
        if rec is None or match_key is None:
            return {"ok": False, "error": f"No se encontró registro WSFE con huella '{huella}' para el CUIT {cuit_em}."}
        if rec.get("estado") not in ("PENDIENTE", "INCIERTO"):
            return {"ok": False, "error": f"El registro ya está resuelto en estado '{rec.get('estado')}'."}

    env_k = ambiente or rec.get("ambiente") or "homologacion"

    if act == "marcar_no_emitido":
        # N4-j + residual P3: consultar ARCA antes de marcar no emitido.
        # Si hay candidato -> avisar; si ARCA devuelve INCIERTO (error/sin confirmación) -> exigir forzar=True.
        if not forzar:
            rec_st, cand = _reconciliar_registro_incierto(
                rec=rec,
                cuit_emisor=cuit_em,
                pto_vta=int(rec["pto_vta"]),
                cbte_tipo=int(rec["cbte_tipo"]),
                doc_nro=int(rec.get("doc_nro", 0)),
                imp_total=float(rec.get("imp_total", 0.0)),
                cbte_fch=str(rec.get("cbte_fch", "")),
                ambiente=env_k,
                now_ts=time.time(),
            )
            if rec_st == "ADOPTADO" and cand is not None:
                return {
                    "ok": False,
                    "candidato_encontrado": True,
                    "cbte_nro_candidato": cand.get("cbte_nro"),
                    "cae_candidato": cand.get("cae"),
                    "error": (
                        f"ATENCIÓN: ARCA tiene el comprobante #{cand.get('cbte_nro')} (CAE {cand.get('cae')}) "
                        "con el mismo importe, receptor y fecha. Usá `accion='adoptar_nro'` en lugar de "
                        "`marcar_no_emitido` (o enviá `forzar: true` si confirmás que es otro comprobante)."
                    ),
                }
            if rec_st != "NO_EMITIDO_CONFIRMADO":
                return {
                    "ok": False,
                    "requiere_forzar": True,
                    "estado_reconciliacion": rec_st,
                    "error": (
                        "No se pudo confirmar en ARCA que el comprobante no fue emitido (reconciliación devolvió INCIERTO). "
                        "Reintentá cuando ARCA responda o enviá `forzar: true` si ya verificaste manualmente en Comprobantes en Línea."
                    ),
                }
        with _idem_io_lock:
            store = _load_store_locked()
            rec["estado"] = "NO_EMITIDO_CONFIRMADO"
            rec["resuelto_manual"] = True
            rec["forzado"] = bool(forzar)
            rec["updated_at"] = time.time()
            store["by_huella"][match_key] = rec
            if rec.get("idempotency_key"):
                kl = f"{env_k}:{cuit_em}:{rec['idempotency_key']}"
                if kl in store["by_key"]:
                    store["by_key"][kl] = rec
            _save_store_locked(store)
        return {
            "ok": True,
            "cuit": cuit_em,
            "huella": match_key[:16],
            "estado": "NO_EMITIDO_CONFIRMADO",
            "mensaje": "Registro marcado manualmente como NO_EMITIDO_CONFIRMADO. Ya podés volver a emitir la venta.",
        }

    # accion == "adoptar_nro"
    if not cbte_nro or int(cbte_nro) <= 0:
        return {"ok": False, "error": "Para 'adoptar_nro' debés indicar el número de comprobante (`cbte_nro`)."}
    comp = arca_ws.consultar_comprobante_por_nro_wsfe(
        cuit_emisor=cuit_em,
        pto_vta=int(rec["pto_vta"]),
        cbte_tipo=int(rec["cbte_tipo"]),
        cbte_nro=int(cbte_nro),
        ambiente=env_k,
    )
    if not comp or not comp.get("cae"):
        return {"ok": False, "error": f"No se encontró el comprobante #{cbte_nro} autorizado en ARCA para adoptarlo."}

    # N4-j: validar importe, documento y fecha contra el registro, salvo forzar=True
    diffs = []
    if abs(round(float(comp.get("imp_total", -1)), 2) - round(float(rec.get("imp_total", 0)), 2)) >= 0.005:
        diffs.append(f"importe ARCA={comp.get('imp_total')} vs registro={rec.get('imp_total')}")
    if int(comp.get("doc_nro", -1)) != int(rec.get("doc_nro", 0)):
        diffs.append(f"doc_nro ARCA={comp.get('doc_nro')} vs registro={rec.get('doc_nro')}")
    if str(comp.get("cbte_fch", "")).strip() != str(rec.get("cbte_fch", "")).strip():
        diffs.append(f"fecha ARCA={comp.get('cbte_fch')} vs registro={rec.get('cbte_fch')}")
    if diffs and not forzar:
        return {
            "ok": False,
            "discrepancia_datos": True,
            "diferencias": diffs,
            "error": (
                f"El comprobante #{cbte_nro} en ARCA no coincide con el registro incierto ({'; '.join(diffs)}). "
                "Verificá el número o reenviá con `forzar: true` para adoptarlo igualmente."
            ),
        }

    adoptado = {
        "ok": True,
        "modo": "EMISION_OFICIAL_WSFEV1",
        "ambiente": env_k,
        "emisor_cuit": cuit_em,
        "punto_venta": int(rec["pto_vta"]),
        "cbte_tipo": int(rec["cbte_tipo"]),
        "cbte_nro": int(cbte_nro),
        "resultado": "APROBADO",
        "cae": str(comp["cae"]),
        "cae_vencimiento": str(comp.get("cae_vencimiento", "")),
        "adoptado": True,
        "resuelto_manual": True,
        "forzado": bool(forzar),
    }
    with _idem_io_lock:
        store = _load_store_locked()
        rec["estado"] = "AUTORIZADO"
        rec["cae"] = adoptado["cae"]
        rec["cbte_nro"] = int(cbte_nro)
        rec["cae_vencimiento"] = adoptado["cae_vencimiento"]
        rec["adoptado"] = True
        rec["resuelto_manual"] = True
        rec["response"] = adoptado
        rec["updated_at"] = time.time()
        store["by_huella"][match_key] = rec
        if rec.get("idempotency_key"):
            kl = f"{env_k}:{cuit_em}:{rec['idempotency_key']}"
            if kl in store["by_key"]:
                store["by_key"][kl] = rec
        _save_store_locked(store)
    return adoptado


def emitir_wsfe_con_idempotencia(
    *,
    cuit_emisor: str,
    pto_vta: int,
    cbte_tipo: int,
    receptor_cuit: str,
    importe_neto: float,
    importe_iva: float,
    concepto: int = 2,
    ambiente: str = "homologacion",
    cbte_asoc: Optional[Dict[str, Any]] = None,
    condicion_iva_receptor_id: Optional[int] = None,
    idempotency_key: str = "",
    reemitir_aunque_duplicado: bool = False,
    cbte_fch: Optional[str] = None,
    wsfe_lock: Optional[threading.Lock] = None,
    on_emit_ok: Optional[Callable[[Dict[str, Any], bool], None]] = None,
) -> Dict[str, Any]:
    """Ejecuta una emisión WSFE confirmada con idempotencia persistente y adopción de CAE (N4)."""
    cuit_em = bv.normalizar_cuit(cuit_emisor)
    env_k = "homologacion" if "homo" in (ambiente or "homologacion").lower() else "produccion"
    doc_tipo, doc_nro = _normalizar_receptor(receptor_cuit)
    imp_total = round(float(importe_neto) + float(importe_iva), 2)
    fecha_cbte = (cbte_fch or arca_ws.fecha_hoy_arca()).strip()
    idem_k = (idempotency_key or "").strip()

    huella_base = calcular_huella_wsfe(
        cuit_emisor=cuit_em,
        pto_vta=pto_vta,
        cbte_tipo=cbte_tipo,
        concepto=concepto,
        doc_tipo=doc_tipo,
        doc_nro=doc_nro,
        imp_total=imp_total,
        cbte_fch=fecha_cbte,
        ambiente=env_k,
    )
    key_lookup = f"{env_k}:{cuit_em}:{idem_k}" if idem_k else ""

    lock_ctx = wsfe_lock if wsfe_lock is not None else threading.Lock()
    with lock_ctx:
        now = time.time()
        with _idem_io_lock:
            store = _load_store_locked()
            existing = None
            cand_h = store["by_huella"].get(huella_base)
            cand_k = store["by_key"].get(key_lookup) if key_lookup else None

            # N4-b + N4-c: PENDIENTE o INCIERTO bloquean por ESTADO sin ventana de tiempo
            # e incluso si reemitir_aunque_duplicado=True (se debe reconciliar primero).
            if isinstance(cand_h, dict) and cand_h.get("estado") in ("PENDIENTE", "INCIERTO"):
                existing = cand_h
            elif isinstance(cand_k, dict) and cand_k.get("estado") in ("PENDIENTE", "INCIERTO"):
                existing = cand_k
            elif not reemitir_aunque_duplicado:
                # La ventana de 10 min aplica solo a AUTORIZADO (replay)
                if isinstance(cand_h, dict) and cand_h.get("estado") == "AUTORIZADO" and (now - float(cand_h.get("created_at") or 0)) <= WSFE_IDEM_WINDOW_SEC:
                    existing = cand_h
                elif isinstance(cand_k, dict) and cand_k.get("estado") == "AUTORIZADO" and (now - float(cand_k.get("created_at") or 0)) <= WSFE_IDEM_RETENTION_SEC:
                    existing = cand_k

        reemitido_post_no_emitido = False
        if existing is not None:
            estado_prev = existing.get("estado")
            if estado_prev == "AUTORIZADO" and isinstance(existing.get("response"), dict):
                out = dict(existing["response"])
                out["replay"] = True
                out["idempotente_reusado"] = True
                return out

            if estado_prev in ("PENDIENTE", "INCIERTO"):
                rec_status, adoptado = _reconciliar_registro_incierto(
                    rec=existing,
                    cuit_emisor=cuit_em,
                    pto_vta=pto_vta,
                    cbte_tipo=cbte_tipo,
                    doc_nro=doc_nro,
                    imp_total=imp_total,
                    cbte_fch=fecha_cbte,
                    ambiente=env_k,
                    now_ts=now,
                )
                if rec_status == "ADOPTADO" and adoptado is not None:
                    with _idem_io_lock:
                        store = _load_store_locked()
                        rec_upd = dict(existing)
                        rec_upd["estado"] = "AUTORIZADO"
                        rec_upd["updated_at"] = time.time()
                        rec_upd["cae"] = adoptado["cae"]
                        rec_upd["cbte_nro"] = adoptado["cbte_nro"]
                        rec_upd["cae_vencimiento"] = adoptado.get("cae_vencimiento", "")
                        rec_upd["adoptado"] = True
                        rec_upd["response"] = adoptado
                        store["by_huella"][huella_base] = rec_upd
                        if key_lookup:
                            store["by_key"][key_lookup] = rec_upd
                        _save_store_locked(store)
                    if on_emit_ok:
                        on_emit_ok(adoptado, False)
                    return adoptado

                if rec_status == "NO_EMITIDO_CONFIRMADO":
                    # N4-f: ARCA confirmó que el intento previo nunca se emitió -> marcar y re-emitir en esta misma llamada
                    with _idem_io_lock:
                        store = _load_store_locked()
                        rec_noem = dict(existing)
                        rec_noem["estado"] = "NO_EMITIDO_CONFIRMADO"
                        rec_noem["updated_at"] = time.time()
                        store["by_huella"][huella_base] = rec_noem
                        if key_lookup:
                            store["by_key"][key_lookup] = rec_noem
                        _save_store_locked(store)
                    reemitido_post_no_emitido = True
                    logger.info(f"[WSFE N4-f] Confirmado NO_EMITIDO_CONFIRMADO para {cuit_em} huella={huella_base[:12]}; re-emitiendo.")
                else:
                    # No se pudo confirmar coincidencia exacta ni no-emisión -> mantener INCIERTO y NUNCA re-emitir
                    with _idem_io_lock:
                        store = _load_store_locked()
                        rec_inc = dict(existing)
                        rec_inc["estado"] = "INCIERTO"
                        rec_inc["updated_at"] = time.time()
                        store["by_huella"][huella_base] = rec_inc
                        if key_lookup:
                            store["by_key"][key_lookup] = rec_inc
                        _save_store_locked(store)
                    return _respuesta_incierta(
                        cuit_emisor=cuit_em,
                        pto_vta=pto_vta,
                        cbte_tipo=cbte_tipo,
                        huella=huella_base,
                        detalle="intento previo sin confirmación coincidente en ARCA",
                    )

        # Paso 1 (N4-h + residual P3): obtener ultimo_nro_antes ANTES de persistir PENDIENTE y llamar a FECAESolicitar.
        # Sin certificado -> CERTIFICADO_PENDIENTE con guía CSR; sin servicio -> ARCA_NO_DISPONIBLE y NO emitir.
        try:
            ultimo_antes = arca_ws.obtener_ultimo_autorizado_wsfe(
                cuit_emisor=cuit_em,
                pto_vta=pto_vta,
                cbte_tipo=cbte_tipo,
                ambiente=env_k,
            )
        except arca_ws.CertificadoPendienteError as exc:
            return {
                "ok": False,
                "estado": "CERTIFICADO_PENDIENTE",
                "cuit": cuit_em,
                "mensaje": str(exc),
            }
        except Exception as exc:
            logger.warning(f"[WSFE N4-h] Error leyendo FECompUltimoAutorizado previo: {exc}")
            return {
                "ok": False,
                "estado": "ARCA_NO_DISPONIBLE",
                "cuit": cuit_em,
                "error": f"No se pudo consultar FECompUltimoAutorizado previo a la emisión ({str(exc)[:160]}). No se emitió ningún comprobante; reintentá en unos segundos.",
            }
        if ultimo_antes is None:
            return {
                "ok": False,
                "estado": "ARCA_NO_DISPONIBLE",
                "cuit": cuit_em,
                "error": "No se pudo obtener FECompUltimoAutorizado previo (certificado o servicio WSFE no disponible). No se emitió ningún comprobante.",
            }

        pend_rec = {
            "huella": huella_base,
            "idempotency_key": idem_k,
            "estado": "PENDIENTE",
            "cuit_emisor": cuit_em,
            "pto_vta": int(pto_vta),
            "cbte_tipo": int(cbte_tipo),
            "doc_tipo": doc_tipo,
            "doc_nro": doc_nro,
            "imp_total": imp_total,
            "cbte_fch": fecha_cbte,
            "ambiente": env_k,
            "ultimo_nro_antes": int(ultimo_antes),
            "override_duplicado": bool(reemitir_aunque_duplicado),
            "intento_at": now,
            "created_at": now,
            "updated_at": now,
        }
        with _idem_io_lock:
            store = _load_store_locked()
            store["by_huella"][huella_base] = pend_rec
            if key_lookup:
                store["by_key"][key_lookup] = pend_rec
            _save_store_locked(store)

        # Paso 2: invocar emisión real WSFEv1 pasando la misma cbte_fch de la huella (N4-e)
        try:
            res = arca_ws.emitir_comprobante_wsfe(
                cuit_emisor=cuit_em,
                pto_vta=pto_vta,
                cbte_tipo=cbte_tipo,
                receptor_cuit=receptor_cuit,
                importe_neto=importe_neto,
                importe_iva=importe_iva,
                concepto=concepto,
                ambiente=env_k,
                confirmado=True,
                cbte_asoc=cbte_asoc,
                condicion_iva_receptor_id=condicion_iva_receptor_id,
                cbte_fch=fecha_cbte,
            )
        except Exception as exc:
            logger.exception(f"[WSFE N4] Error/timeout tras persistir PENDIENTE para {cuit_em}")
            with _idem_io_lock:
                store = _load_store_locked()
                inc_rec = dict(pend_rec)
                inc_rec["estado"] = "INCIERTO"
                inc_rec["updated_at"] = time.time()
                inc_rec["error"] = str(exc)[:300]
                store["by_huella"][huella_base] = inc_rec
                if key_lookup:
                    store["by_key"][key_lookup] = inc_rec
                _save_store_locked(store)
            return _respuesta_incierta(
                cuit_emisor=cuit_em,
                pto_vta=pto_vta,
                cbte_tipo=cbte_tipo,
                huella=huella_base,
                detalle=str(exc)[:180],
            )

        # Paso 3: persistir resultado definitivo ANTES de soltar el lock
        is_aprobado = isinstance(res, dict) and (
            bool(res.get("cae")) and (res.get("ok") is True or res.get("resultado") == "APROBADO")
        )
        is_incierto = isinstance(res, dict) and (
            res.get("resultado") == "INCIERTO" or res.get("incierto") is True
        )
        is_rechazado = (not is_incierto) and isinstance(res, dict) and (
            res.get("resultado") == "RECHAZADO" or res.get("estado") == "CERTIFICADO_PENDIENTE" or res.get("ok") is False
        )

        with _idem_io_lock:
            store = _load_store_locked()
            fin_rec = dict(pend_rec)
            fin_rec["updated_at"] = time.time()
            if is_aprobado:
                out_ok = dict(res)
                out_ok["ok"] = True
                if reemitido_post_no_emitido:
                    out_ok["reemitido_tras_no_emitido_confirmado"] = True
                fin_rec["estado"] = "AUTORIZADO"
                fin_rec["cae"] = str(out_ok.get("cae", ""))
                fin_rec["cbte_nro"] = out_ok.get("cbte_nro")
                fin_rec["cae_vencimiento"] = out_ok.get("cae_vencimiento", "")
                fin_rec["response"] = out_ok
                store["by_huella"][huella_base] = fin_rec
                if key_lookup:
                    store["by_key"][key_lookup] = fin_rec
                _save_store_locked(store)
                res = out_ok
            elif is_rechazado:
                fin_rec["estado"] = "RECHAZADO"
                fin_rec["response"] = res
                store["by_huella"][huella_base] = fin_rec
                if key_lookup:
                    store["by_key"][key_lookup] = fin_rec
                _save_store_locked(store)
            else:
                fin_rec["estado"] = "INCIERTO"
                fin_rec["response"] = res if isinstance(res, dict) else {"raw": str(res)}
                store["by_huella"][huella_base] = fin_rec
                if key_lookup:
                    store["by_key"][key_lookup] = fin_rec
                _save_store_locked(store)

        if is_aprobado and on_emit_ok:
            on_emit_ok(res, bool(reemitir_aunque_duplicado))
        return res
