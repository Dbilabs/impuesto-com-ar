"""
bot/eventanilla_ws.py
Cliente SOAP estricto para e-Ventanilla de ARCA (`veconsumerws` — Fase 3.4).

WSDL verificados (HTTP 200):
  - Producción:   https://infraestructura.afip.gob.ar/ve-ws/services/veconsumer
  - Homologación: https://stable-middleware-tecno-ext.afip.gob.ar/ve-ws/services/veconsumer
  - Namespace:    http://ve.tecno.afip.gov.ar/domain/service/ws
  - WSAA service: veconsumerws (certificado propio vía autenticar_wsaa_para_cuit)

CUIDADO LEGAL:
  - `consultar_comunicaciones_ve` (consultarComunicaciones) consulta SOLO metadatos
    sin abrir el contenido (no perfecciona notificación).
  - `consumir_comunicacion_ve` (consumirComunicacion) abre el contenido y puede
    perfeccionar la notificación en DFE -> solo debe invocarse desde `abrir_comunicacion_dfe`
    con `confirmado=True` estricto y aviso legal explícito.
"""

import base64
import gzip
import hashlib
import logging
import time
import urllib.error
import xml.etree.ElementTree as ET
import zlib
from typing import Any, Dict, List, Optional

from . import arca_ws
from . import boveda_segura as bv

logger = logging.getLogger("impuesto.eventanilla_ws")

VE_NS = "http://ve.tecno.afip.gov.ar/domain/service/ws"
VE_ESTADOS_TTL_SEC = 86400.0        # 24 h
MAX_ADJUNTO_BYTES = 10 * 1024 * 1024  # 10 MB por adjunto
_VE_ESTADOS_CACHE: Dict[str, tuple[float, Dict[str, str]]] = {}


class VeConsumerResponseError(RuntimeError):
    """Error explícito de veconsumerws (Fault, HTTP 500, XML malformado, totalItems>0 vacío, auth o md5)."""


class VeConsumerUnavailableError(RuntimeError):
    """Error de red/timeout en veconsumerws: habilita fallback al scraper de DFE en Playwright."""


def _endpoint_ve(ambiente: str) -> str:
    env_key = "homologacion" if "homo" in (ambiente or "produccion").lower() else "produccion"
    return arca_ws.ENDPOINTS[env_key]["veconsumerws"]


def _post_ve_soap(ambiente: str, soap_xml: str, soap_action: str = "") -> str:
    url = _endpoint_ve(ambiente)
    try:
        return arca_ws._soap_post(url, soap_xml, soap_action=soap_action, timeout=20)
    except urllib.error.HTTPError as http_err:
        body = ""
        try:
            body = http_err.read().decode("utf-8", errors="ignore")[:300]
        except Exception:
            pass
        if http_err.code in (401, 403, 500):
            raise VeConsumerResponseError(f"veconsumerws HTTP {http_err.code}: {body or http_err.reason}") from http_err
        raise VeConsumerUnavailableError(f"veconsumerws HTTP {http_err.code}: {http_err.reason}") from http_err
    except Exception as exc:
        raise VeConsumerUnavailableError(f"veconsumerws no disponible: {exc}") from exc


def _parse_xml_strict(raw_xml: str) -> ET.Element:
    if not raw_xml or not raw_xml.strip():
        raise VeConsumerResponseError("Respuesta vacía de veconsumerws.")
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError as exc:
        raise VeConsumerResponseError(f"XML malformado en veconsumerws: {exc}") from exc
    for el in root.iter():
        if el.tag.split("}")[-1] == "Fault":
            msg = " ".join(t.strip() for t in el.itertext() if t and t.strip())[:300]
            raise VeConsumerResponseError(f"SOAP Fault en veconsumerws: {msg}")
    return root


def _child_text(parent: ET.Element, *names: str) -> str:
    want = {n.lower() for n in names}
    for ch in parent:
        if ch.tag.split("}")[-1].lower() in want and ch.text is not None:
            return ch.text.strip()
    return ""


def _parse_bool_xml(val: str) -> bool:
    return (val or "").strip().lower() in ("true", "1", "s", "si", "yes")


def consultar_estados_ve(
    cuit: str,
    ambiente: str = "produccion",
    auth: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Consulta y cachea por 24 h el catálogo de estados de e-Ventanilla (`consultarEstados`)."""
    env_key = "homologacion" if "homo" in (ambiente or "produccion").lower() else "produccion"
    hit = _VE_ESTADOS_CACHE.get(env_key)
    if hit and (time.time() - hit[0]) < VE_ESTADOS_TTL_SEC:
        return dict(hit[1])

    cuit_clean = bv.normalizar_cuit(cuit)
    ta = auth or arca_ws.autenticar_wsaa_para_cuit(cuit_clean, service="veconsumerws", ambiente=env_key)
    soap = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ws="{VE_NS}">
   <soapenv:Header/>
   <soapenv:Body>
      <ws:consultarEstados>
         <authRequest>
            <token>{ta['token']}</token>
            <sign>{ta['sign']}</sign>
            <cuitRepresentada>{cuit_clean}</cuitRepresentada>
         </authRequest>
      </ws:consultarEstados>
   </soapenv:Body>
</soapenv:Envelope>"""
    raw = _post_ve_soap(env_key, soap, soap_action="consultarEstados")
    root = _parse_xml_strict(raw)
    estados: Dict[str, str] = {}
    for el in root.iter():
        if el.tag.split("}")[-1].lower() in ("estado", "item", "estadoitem"):
            eid = _child_text(el, "id", "codigo", "estado")
            edesc = _child_text(el, "descripcion", "desc", "estadoDesc")
            if eid and edesc:
                estados[eid] = edesc
    if estados:
        _VE_ESTADOS_CACHE[env_key] = (time.time(), dict(estados))
    return estados


def parsear_consultar_comunicaciones(raw_xml: str, estados_map: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Parser estricto de `consultarComunicacionesResponse` (RespuestaPaginada)."""
    root = _parse_xml_strict(raw_xml)
    resp_el = None
    for el in root.iter():
        tl = el.tag.split("}")[-1].lower()
        if tl in ("respuestapaginada", "return", "consultarcomunicacionesreturn", "consultarcomunicacionesresult"):
            resp_el = el
            break
    if resp_el is None:
        raise VeConsumerResponseError("Respuesta de veconsumerws sin nodo RespuestaPaginada/return.")

    pagina = int(_child_text(resp_el, "pagina") or "1")
    total_paginas = int(_child_text(resp_el, "totalPaginas") or "1")
    total_items_str = _child_text(resp_el, "totalItems")
    if total_items_str == "" or not total_items_str.isdigit():
        raise VeConsumerResponseError("Respuesta de veconsumerws sin totalItems válido.")
    total_items = int(total_items_str)

    items_out: List[Dict[str, Any]] = []
    for el in resp_el.iter():
        if el.tag.split("}")[-1].lower() in ("item", "comunicacionsimplificada"):
            cid = _child_text(el, "idComunicacion", "id")
            if not cid:
                continue
            est = _child_text(el, "estado")
            est_desc = _child_text(el, "estadoDesc") or (estados_map or {}).get(est, "")
            items_out.append({
                "id": cid,
                "cuit_destinatario": _child_text(el, "cuitDestinatario"),
                "asunto": _child_text(el, "asunto"),
                "fecha_publicacion": _child_text(el, "fechaPublicacion"),
                "fecha_vencimiento": _child_text(el, "fechaVencimiento") or None,
                "estado": est,
                "estado_desc": est_desc or est,
                "organismo": _child_text(el, "sistemaPublicadorDesc", "sistemaPublicador"),
                "tiene_adjunto": _parse_bool_xml(_child_text(el, "tieneAdjunto")),
                "prioridad": _child_text(el, "prioridad") or None,
            })

    # Regla estricta (igual que WSAPOC/N4-g): totalItems > 0 con items vacío -> error explícito
    if total_items > 0 and not items_out:
        raise VeConsumerResponseError(
            f"veconsumerws informó totalItems={total_items} pero no devolvió ítems parseables (nunca informar 'sin notificaciones')."
        )

    return {
        "pagina": pagina,
        "total_paginas": max(1, total_paginas),
        "total_items": total_items,
        "items": items_out,
    }


def consultar_comunicaciones_ve(
    cuit: str,
    *,
    ambiente: str = "produccion",
    max_paginas: int = 10,
    resultados_por_pagina: int = 50,
    estado: Optional[str] = None,
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
) -> Dict[str, Any]:
    """Lista comunicaciones del DFE vía `consultarComunicaciones` (SOLO metadatos, NO perfecciona notificación).
    Pagina hasta `max_paginas` x `resultados_por_pagina` (10 x 50)."""
    cuit_clean = bv.normalizar_cuit(cuit)
    if len(cuit_clean) != 11:
        return {"ok": False, "error": "CUIT inválido (debe tener 11 dígitos)."}
    env_key = "homologacion" if "homo" in (ambiente or "produccion").lower() else "produccion"

    ta = arca_ws.autenticar_wsaa_para_cuit(cuit_clean, service="veconsumerws", ambiente=env_key)
    try:
        estados_map = consultar_estados_ve(cuit_clean, ambiente=env_key, auth=ta)
    except Exception:
        estados_map = {}

    all_items: List[Dict[str, Any]] = []
    total_items = 0
    pagina_actual = 1
    total_paginas = 1

    while pagina_actual <= total_paginas and pagina_actual <= max_paginas:
        filtros = [f"<pagina>{pagina_actual}</pagina>", f"<resultadosPorPagina>{int(resultados_por_pagina)}</resultadosPorPagina>"]
        if estado:
            filtros.append(f"<estado>{estado}</estado>")
        if fecha_desde:
            filtros.append(f"<fechaDesde>{fecha_desde}</fechaDesde>")
        if fecha_hasta:
            filtros.append(f"<fechaHasta>{fecha_hasta}</fechaHasta>")
        soap = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ws="{VE_NS}">
   <soapenv:Header/>
   <soapenv:Body>
      <ws:consultarComunicaciones>
         <authRequest>
            <token>{ta['token']}</token>
            <sign>{ta['sign']}</sign>
            <cuitRepresentada>{cuit_clean}</cuitRepresentada>
         </authRequest>
         <filter>
            {''.join(filtros)}
         </filter>
      </ws:consultarComunicaciones>
   </soapenv:Body>
</soapenv:Envelope>"""
        raw = _post_ve_soap(env_key, soap, soap_action="consultarComunicaciones")
        parsed = parsear_consultar_comunicaciones(raw, estados_map=estados_map)
        total_items = parsed["total_items"]
        total_paginas = parsed["total_paginas"]
        all_items.extend(parsed["items"])
        if total_items == 0 or pagina_actual >= total_paginas:
            break
        pagina_actual += 1

    out = {
        "ok": True,
        "cuit": cuit_clean,
        "notificaciones": all_items,
        "total": total_items,
        "paginas_leidas": min(pagina_actual, max_paginas),
        "truncado": bool(total_paginas > max_paginas),
        "fuente": "VECONSUMERWS",
        "fuente_certificado": ta.get("fuente_certificado", "global_delegado"),
        "nota_legal": "Solo metadatos (consultarComunicaciones). Para abrir el contenido usá `abrir_comunicacion_dfe` con confirmado=true.",
    }
    if ta.get("alerta_vencimiento"):
        out["alerta_vencimiento"] = ta["alerta_vencimiento"]
    return out


def parsear_consumir_comunicacion(raw_xml: str, incluir_adjuntos: bool = False) -> Dict[str, Any]:
    """Parser estricto de `consumirComunicacionResponse` con verificación de md5, contentSize y tope 10 MB en memoria."""
    root = _parse_xml_strict(raw_xml)
    com_el = None
    for el in root.iter():
        tl = el.tag.split("}")[-1].lower()
        if tl in ("comunicacion", "return", "consumircomunicacionreturn", "consumircomunicacionresult"):
            com_el = el
            break
    if com_el is None:
        raise VeConsumerResponseError("Respuesta de veconsumerws sin nodo Comunicacion.")

    mensaje = _child_text(com_el, "mensaje")
    tiempo_vida = _child_text(com_el, "tiempoDeVida") or None

    adjuntos_out: List[Dict[str, Any]] = []
    for el in com_el.iter():
        if el.tag.split("}")[-1].lower() in ("adjunto", "adjuntos"):
            fname = _child_text(el, "filename")
            if not fname:
                continue
            compressed = _parse_bool_xml(_child_text(el, "compressed"))
            signed = _parse_bool_xml(_child_text(el, "signed"))
            encrypted = _parse_bool_xml(_child_text(el, "encrypted"))
            md5_expected = _child_text(el, "md5").lower()
            size_str = _child_text(el, "contentSize")
            content_b64 = _child_text(el, "content")

            adj_meta: Dict[str, Any] = {
                "filename": fname,
                "compressed": compressed,
                "signed": signed,
                "encrypted": encrypted,
                "md5": md5_expected or None,
                "content_size": int(size_str) if size_str.isdigit() else None,
            }

            if incluir_adjuntos and content_b64:
                try:
                    raw_bytes = base64.b64decode(content_b64, validate=True)
                except Exception as exc:
                    raise VeConsumerResponseError(f"Adjunto '{fname}' con base64 inválido: {exc}") from exc

                if len(raw_bytes) > MAX_ADJUNTO_BYTES:
                    raise VeConsumerResponseError(f"Adjunto '{fname}' excede el tope de 10 MB ({len(raw_bytes)} bytes).")

                if size_str.isdigit() and len(raw_bytes) != int(size_str):
                    raise VeConsumerResponseError(
                        f"Adjunto '{fname}': contentSize declarado ({size_str}) no coincide con bytes recibidos ({len(raw_bytes)})."
                    )

                if md5_expected:
                    md5_actual = hashlib.md5(raw_bytes).hexdigest().lower()
                    if md5_actual != md5_expected:
                        raise VeConsumerResponseError(
                            f"Adjunto '{fname}': checksum MD5 desparejo (esperado={md5_expected}, real={md5_actual})."
                        )

                final_bytes = raw_bytes
                if compressed:
                    # P3: descompresión acotada en memoria (zlib.decompressobj con max_length = 10 MB + 1) contra zip bombs
                    try:
                        decomp = zlib.decompressobj(zlib.MAX_WBITS | 32)  # soporta gzip y zlib
                        final_bytes = decomp.decompress(raw_bytes, MAX_ADJUNTO_BYTES + 1)
                        if len(final_bytes) > MAX_ADJUNTO_BYTES or decomp.unconsumed_tail:
                            raise VeConsumerResponseError(f"Adjunto '{fname}' descomprimido excede el tope de 10 MB.")
                        rem = decomp.flush(MAX_ADJUNTO_BYTES + 1 - len(final_bytes))
                        final_bytes += rem
                        if len(final_bytes) > MAX_ADJUNTO_BYTES:
                            raise VeConsumerResponseError(f"Adjunto '{fname}' descomprimido excede el tope de 10 MB.")
                    except VeConsumerResponseError:
                        raise
                    except Exception as exc:
                        raise VeConsumerResponseError(f"No se pudo descomprimir adjunto '{fname}': {exc}") from exc

                adj_meta["content_base64"] = base64.b64encode(final_bytes).decode("ascii")
                adj_meta["bytes_finales"] = len(final_bytes)

            adjuntos_out.append(adj_meta)

    return {
        "mensaje": mensaje,
        "tiempo_de_vida": tiempo_vida,
        "adjuntos": adjuntos_out,
    }


def consumir_comunicacion_ve(
    cuit: str,
    id_comunicacion: int,
    *,
    incluir_adjuntos: bool = False,
    ambiente: str = "produccion",
) -> Dict[str, Any]:
    """Abre el contenido de una comunicación DFE vía `consumirComunicacion` (MUTANTE: puede perfeccionar notificación)."""
    cuit_clean = bv.normalizar_cuit(cuit)
    env_key = "homologacion" if "homo" in (ambiente or "produccion").lower() else "produccion"
    ta = arca_ws.autenticar_wsaa_para_cuit(cuit_clean, service="veconsumerws", ambiente=env_key)
    inc_str = "true" if incluir_adjuntos else "false"
    soap = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ws="{VE_NS}">
   <soapenv:Header/>
   <soapenv:Body>
      <ws:consumirComunicacion>
         <authRequest>
            <token>{ta['token']}</token>
            <sign>{ta['sign']}</sign>
            <cuitRepresentada>{cuit_clean}</cuitRepresentada>
         </authRequest>
         <idComunicacion>{int(id_comunicacion)}</idComunicacion>
         <incluirAdjuntos>{inc_str}</incluirAdjuntos>
      </ws:consumirComunicacion>
   </soapenv:Body>
</soapenv:Envelope>"""
    raw = _post_ve_soap(env_key, soap, soap_action="consumirComunicacion")
    parsed = parsear_consumir_comunicacion(raw, incluir_adjuntos=incluir_adjuntos)
    return {
        "ok": True,
        "cuit": cuit_clean,
        "id_comunicacion": int(id_comunicacion),
        "fuente": "VECONSUMERWS",
        "fuente_certificado": ta.get("fuente_certificado", "global_delegado"),
        "aviso_legal": "Comunicación abierta vía consumirComunicacion; ARCA puede considerarla formalmente notificada desde este momento.",
        **parsed,
    }
