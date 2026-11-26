"""
Módulo de Facturación Electrónica para Empresas y Monotributistas (impuesto.com.ar)
Permite a los agentes (Claude, ChatGPT) emitir facturas A, B, C y Notas de Crédito,
determinando alícuotas de IVA, puntos de venta y generando el comprobante oficial con CAE y QR.
"""

import os
import json
import base64
import datetime
from typing import Dict, Any, List, Optional

# Alícuotas de IVA vigentes en Argentina (ARCA / AFIP)
ALICUOTAS_IVA = {
    "21": {"id": 5, "tasa": 0.21, "desc": "21%"},
    "10.5": {"id": 4, "tasa": 0.105, "desc": "10.5%"},
    "27": {"id": 6, "tasa": 0.27, "desc": "27% (Telecomunicaciones, Energía)"},
    "0": {"id": 3, "tasa": 0.0, "desc": "0% / No Gravado"},
    "exento": {"id": 2, "tasa": 0.0, "desc": "Exento"}
}

def determinar_tipo_comprobante(condicion_emisor: str, condicion_receptor: str, operacion: str = "FACTURA") -> Dict[str, Any]:
    """
    Determina si corresponde Factura A, B, C o E según la normativa de ARCA (RG 1415 / Ley de IVA).
    """
    e = condicion_emisor.upper()
    r = condicion_receptor.upper()

    if "MONOTRIBUTO" in e:
        # Monotributistas siempre emiten C (o E para exportación)
        if "EXTERIOR" in r or "EXPORTACION" in r:
            return {"tipo": "Factura E", "codigo": 19, "discrimina_iva": False, "letra": "E"}
        return {"tipo": "Factura C", "codigo": 11, "discrimina_iva": False, "letra": "C"}

    # Emisor Responsable Inscripto (Empresas S.R.L., S.A., Personas Jurídicas)
    if "EXTERIOR" in r or "EXPORTACION" in r:
        return {"tipo": "Factura E", "codigo": 19, "discrimina_iva": False, "letra": "E"}

    if "INSCRIPTO" in r or "RESPONSABLE INSCRIPTO" in r:
        # Venta entre Responsables Inscriptos: FACTURA A (discrimina IVA)
        return {"tipo": "Factura A", "codigo": 1, "discrimina_iva": True, "letra": "A"}
    else:
        # Venta a Consumidor Final, Monotributista o Exento: FACTURA B (IVA incluido)
        return {"tipo": "Factura B", "codigo": 6, "discrimina_iva": False, "letra": "B"}

def calcular_totales_factura(
    items: List[Dict[str, Any]],
    discrimina_iva: bool,
    concepto: str = "Servicios",
    retenciones_percepciones: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Calcula Subtotales, IVA discriminado por alícuota y Total general de la factura.
    """
    neto_21 = 0.0
    neto_10_5 = 0.0
    neto_27 = 0.0
    iva_21 = 0.0
    iva_10_5 = 0.0
    iva_27 = 0.0
    no_gravado = 0.0
    exento = 0.0

    items_procesados = []

    for item in items:
        cant = float(item.get("cantidad", 1))
        precio_unit = float(item.get("precio_unitario", 0))
        subtotal = cant * precio_unit
        alic_str = str(item.get("alicuota_iva", "21")).replace("%", "").strip()

        if alic_str == "21":
            neto_21 += subtotal
            iva_21 += subtotal * 0.21
        elif alic_str in ["10.5", "10,5"]:
            neto_10_5 += subtotal
            iva_10_5 += subtotal * 0.105
        elif alic_str == "27":
            neto_27 += subtotal
            iva_27 += subtotal * 0.27
        elif alic_str in ["0", "no_gravado"]:
            no_gravado += subtotal
        elif alic_str in ["exento", "ex"]:
            exento += subtotal
        else:
            neto_21 += subtotal
            iva_21 += subtotal * 0.21

        items_procesados.append({
            "descripcion": item.get("descripcion", "Servicio o producto"),
            "cantidad": cant,
            "precio_unitario": precio_unit,
            "alicuota_iva": alic_str + "%",
            "subtotal": round(subtotal, 2)
        })

    neto_gravado_total = neto_21 + neto_10_5 + neto_27
    iva_total = iva_21 + iva_10_5 + iva_27
    total = neto_gravado_total + iva_total + no_gravado + exento

    # Sumar percepciones si aplican (ej. IIBB CABA/ARBA)
    total_percepciones = 0.0
    if retenciones_percepciones:
        for p in retenciones_percepciones:
            total_percepciones += float(p.get("importe", 0))
    total += total_percepciones

    return {
        "items": items_procesados,
        "neto_gravado": round(neto_gravado_total, 2),
        "detalle_iva": {
            "iva_21": round(iva_21, 2) if neto_21 > 0 else 0.0,
            "iva_10_5": round(iva_10_5, 2) if neto_10_5 > 0 else 0.0,
            "iva_27": round(iva_27, 2) if neto_27 > 0 else 0.0,
            "iva_total": round(iva_total, 2)
        },
        "no_gravado": round(no_gravado, 2),
        "exento": round(exento, 2),
        "total_percepciones": round(total_percepciones, 2),
        "total_factura": round(total, 2),
        "total_factura_fmt": f"${total:,.2f}"
    }

def armar_borrador_factura(
    emisor_cuit: str,
    emisor_razon_social: str,
    emisor_condicion: str,
    receptor_cuit: str,
    receptor_razon_social: str,
    receptor_condicion: str,
    receptor_domicilio: str,
    items: List[Dict[str, Any]],
    punto_venta: int = 1,
    concepto: str = "Servicios",
    forma_pago: str = "Cuenta Corriente / Transferencia",
    cbu_cobranza: Optional[str] = None
) -> Dict[str, Any]:
    """
    Crea un borrador fiscal verificado listo para ser aprobado por el usuario
    antes de ser enviado a ARCA para obtener el CAE.
    """
    tipo_info = determinar_tipo_comprobante(emisor_condicion, receptor_condicion)
    totales = calcular_totales_factura(items, discrimina_iva=tipo_info["discrimina_iva"], concepto=concepto)

    fecha_hoy = datetime.date.today().strftime("%d/%m/%Y")

    borrador = {
        "estado": "BORRADOR_PENDIENTE_CONFIRMACION",
        "comprobante": {
            "letra": tipo_info["letra"],
            "tipo_nombre": tipo_info["tipo"],
            "codigo_afip": tipo_info["codigo"],
            "punto_venta": punto_venta,
            "punto_venta_fmt": f"{punto_venta:05d}",
            "fecha_emision": fecha_hoy,
            "concepto": concepto
        },
        "emisor": {
            "razon_social": emisor_razon_social,
            "cuit": emisor_cuit,
            "condicion_iva": emisor_condicion,
            "cbu_cobranza": cbu_cobranza
        },
        "receptor": {
            "razon_social": receptor_razon_social,
            "cuit": receptor_cuit,
            "condicion_iva": receptor_condicion,
            "domicilio": receptor_domicilio
        },
        "condiciones_comerciales": {
            "forma_pago": forma_pago,
            "vencimiento_pago": (datetime.date.today() + datetime.timedelta(days=15)).strftime("%d/%m/%Y")
        },
        "items": totales["items"],
        "resumen_liquidatorio": {
            "subtotal_neto": totales["neto_gravado"],
            "iva_liquidado": totales["detalle_iva"]["iva_total"],
            "detalle_iva": totales["detalle_iva"],
            "total_a_cobrar": totales["total_factura"],
            "total_a_cobrar_fmt": totales["total_factura_fmt"]
        },
        "impacto_fiscal": {
            "debito_fiscal_generado": totales["detalle_iva"]["iva_total"] if tipo_info["discrimina_iva"] else round(totales["total_factura"] * 0.21 / 1.21, 2),
            "incorporacion_automatica": ["Libro IVA Digital Ventas", "Formulario 2002 IVA Período Actual"]
        },
        "accion_siguiente": "Para emitir oficialmente en ARCA y obtener el CAE, responde 'CONFIRMAR EMISION'."
    }
    return borrador

def generar_datos_qr_arca(cuit_emisor: str, codigo_comprobante: int, pto_vta: int, numero_cmp: int, importe: float, cae: str, fecha: str) -> str:
    """
    Genera el string JSON Base64 oficial de ARCA para el código QR reglamentario (RG 4597).
    """
    data = {
        "ver": 1,
        "fecha": fecha,
        "cuit": int(cuit_emisor.replace("-", "")),
        "ptoVta": pto_vta,
        "tipoCmp": codigo_comprobante,
        "nroCmp": numero_cmp,
        "importe": importe,
        "moneda": "PES",
        "ctz": 1,
        "tipoDocRec": 80,
        "nroDocRec": 0,
        "tipoCodAut": "E",
        "codAut": int(cae) if cae.isdigit() else 0
    }
    raw_json = json.dumps(data)
    b64 = base64.b64encode(raw_json.encode("utf-8")).decode("utf-8")
    return f"https://www.afip.gob.ar/fe/qr/?p={b64}"
