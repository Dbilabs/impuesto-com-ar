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

WSFE_IDEM_WINDOW_SEC = 600.0     # 10 minutos para replay / reconciliación por huella
WSFE_IDEM_RETENTION_SEC = 86400.0  # 24 horas de retención en disco
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
) -> Optional[Dict[str, Any]]:
    """Intenta reconciliar un PENDIENTE/INCIERTO contra ARCA (FECompUltimoAutorizado + FECompConsultar).
    Retorna dict AUTORIZADO con `adoptado=True` si coincide exactamente ImpTotal, DocNro y CbteFch; si no, None."""
    ultimo_antes = rec.get("ultimo_nro_antes")
    if ultimo_antes is None:
        return None
    try:
        ultimo_ahora = arca_ws.obtener_ultimo_autorizado_wsfe(
            cuit_emisor=cuit_emisor,
            pto_vta=pto_vta,
            cbte_tipo=cbte_tipo,
            ambiente=ambiente,
        )
    except Exception as exc:
        logger.warning(f"[WSFE N4] Error consultando FECompUltimoAutorizado para reconciliar: {exc}")
        return None

    if ultimo_ahora is None or int(ultimo_ahora) <= int(ultimo_antes):
        return None

    # Consultar desde el último autorizado hacia atrás hasta ultimo_antes + 1 (máx. 5 comprobantes)
    desde = max(int(ultimo_antes) + 1, int(ultimo_ahora) - 4)
    for nro in range(int(ultimo_ahora), desde - 1, -1):
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
            return None
        if not comp or not comp.get("cae"):
            continue
        imp_match = abs(round(float(comp.get("imp_total", -1)), 2) - round(float(imp_total), 2)) < 0.005
        doc_match = int(comp.get("doc_nro", -1)) == int(doc_nro)
        fch_match = str(comp.get("cbte_fch", "")).strip() == str(cbte_fch).strip()
        if imp_match and doc_match and fch_match:
            return {
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
    return None


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

        if existing is not None:
            estado_prev = existing.get("estado")
            if estado_prev == "AUTORIZADO" and isinstance(existing.get("response"), dict):
                out = dict(existing["response"])
                out["replay"] = True
                out["idempotente_reusado"] = True
                return out

            if estado_prev in ("PENDIENTE", "INCIERTO"):
                adoptado = _reconciliar_registro_incierto(
                    rec=existing,
                    cuit_emisor=cuit_em,
                    pto_vta=pto_vta,
                    cbte_tipo=cbte_tipo,
                    doc_nro=doc_nro,
                    imp_total=imp_total,
                    cbte_fch=fecha_cbte,
                    ambiente=env_k,
                )
                if adoptado is not None:
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

                # No se pudo confirmar coincidencia exacta -> marcar INCIERTO y NUNCA re-emitir
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

        # Paso 1: obtener ultimo_nro_antes ANTES de persistir PENDIENTE y llamar a FECAESolicitar
        ultimo_antes: Optional[int] = None
        try:
            ultimo_antes = arca_ws.obtener_ultimo_autorizado_wsfe(
                cuit_emisor=cuit_em,
                pto_vta=pto_vta,
                cbte_tipo=cbte_tipo,
                ambiente=env_k,
            )
        except Exception as exc:
            logger.warning(f"[WSFE N4] No se pudo leer FECompUltimoAutorizado previo: {exc}")

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
            "ultimo_nro_antes": ultimo_antes,
            "override_duplicado": bool(reemitir_aunque_duplicado),
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
