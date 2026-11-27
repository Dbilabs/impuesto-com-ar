"""
bot/validador_invariantes.py
Motor de Invariantes Contables y Detección de Contradicciones en Tiempo Real.

Principio de calidad de impuesto.com.ar (aplicable a ARCA, AGIP, ARBA, SIFERE y cualquier organismo):
Ningún resultado extraído de un portal fiscal puede entregarse como "válido" sin pasar
controles matemáticos y de coherencia cruzada entre módulos.

Si un parser omite filas (ej. un prefijo '+' en CCMA), si dos módulos se contradicen
(ej. CCMA muestra Monotributo pero Portal Monotributo devuelve 'No detectada'), o si
los subtotales no cuadran con el total oficial del organismo, este validador lo detecta
en milisegundos, registra el incidente para corrección automática y avisa con transparencia.
"""

import os
import json
import datetime
import threading
from pathlib import Path
from typing import Dict, Any, List

INCIDENTES_FILE = Path(__file__).resolve().parent.parent / "data" / "incidentes_calidad.json"
_inc_lock = threading.Lock()


def registrar_incidente_calidad(origen: str, alertas: List[Dict[str, Any]], contexto: Dict[str, Any] = None):
    """Persiste incidentes de cuadre/parser de forma atómica (sin datos sensibles) para mejora continua."""
    if not alertas:
        return
    try:
        with _inc_lock:
            INCIDENTES_FILE.parent.mkdir(parents=True, exist_ok=True)
            prev = []
            if INCIDENTES_FILE.exists():
                prev = json.loads(INCIDENTES_FILE.read_text(encoding="utf-8"))
            prev.append({
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "origen": origen,
                "alertas": alertas,
                "contexto": contexto or {},
            })
            tmp = INCIDENTES_FILE.with_suffix(f".tmp.{os.getpid()}.{threading.get_ident()}")
            tmp.write_text(json.dumps(prev[-200:], ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, INCIDENTES_FILE)
    except Exception:
        pass


def validar_invariantes_auditoria(resultado: Dict[str, Any], tolerancia_pesos: float = 5.0) -> Dict[str, Any]:
    """
    Ejecuta controles de cuadre contable y coherencia cruzada sobre una auditoría integral.
    """
    alertas: List[Dict[str, Any]] = []

    ccma = resultado.get("ccma") or {}
    mf = resultado.get("mis_facilidades") or {}
    mono = resultado.get("portal_monotributo") or {}

    # Invariante 1: Cuadre CCMA (Monotributo vencido + Autónomos vencido == Total Saldo Deudor)
    if "saldo_deudor_vencido" in ccma and "desglose_por_regimen" in ccma:
        total_oficial = float(ccma.get("saldo_deudor_vencido") or 0.0)
        desg = ccma.get("desglose_por_regimen") or {}
        suma_desglose = float(desg.get("monotributo_vencido_total") or 0.0) + float(desg.get("autonomos_vencido_total") or 0.0)
        diff = round(abs(total_oficial - suma_desglose), 2)
        if total_oficial > 0 and diff > tolerancia_pesos:
            alertas.append({
                "codigo": "INV_CCMA_DESCUADRE",
                "severidad": "ALTA",
                "detalle": f"Total Saldo Deudor CCMA (${total_oficial:,.2f}) difiere de la suma desglosada (${suma_desglose:,.2f}) en ${diff:,.2f}. Posible formato de fila no contemplado por el parser."
            })

    # Invariante 2: Cuadre Capital + Accesorios == Total Saldo Deudor CCMA
    if "saldo_deudor_vencido" in ccma and "capital_mensual" in ccma and "intereses_accesorios" in ccma:
        tot = float(ccma.get("saldo_deudor_vencido") or 0.0)
        cap_int = float(ccma.get("capital_mensual") or 0.0) + float(ccma.get("intereses_accesorios") or 0.0)
        if tot > 0 and abs(tot - cap_int) > tolerancia_pesos:
            alertas.append({
                "codigo": "INV_CCMA_CAPITAL_INTERES",
                "severidad": "MEDIA",
                "detalle": f"Capital + Accesorios (${cap_int:,.2f}) no coincide con Total Saldo Deudor (${tot:,.2f})."
            })

    # Invariante 3: Coherencia cruzada CCMA <-> Portal Monotributo
    desg = ccma.get("desglose_por_regimen") or {}
    if float(desg.get("monotributo_vencido_total") or 0.0) > 0:
        cat = str(mono.get("categoria") or "")
        if not cat or cat == "No detectada":
            alertas.append({
                "codigo": "INV_CRUCE_MONO_FALTANTE",
                "severidad": "ALTA",
                "detalle": "CCMA registra deuda de Monotributo pero Portal Monotributo devolvió categoría 'No detectada' (probable fallo de sesión/renderizado en admin_mono)."
            })

    # Invariante 4: Coherencia cruzada CCMA (PFP Mis Facilidades) <-> Mis Facilidades
    if ccma.get("tiene_pfp_mis_facilidades") and mf.get("cantidad_planes_vigentes", 0) == 0 and not mf.get("error"):
        alertas.append({
            "codigo": "INV_CRUCE_PFP_SIN_PLANES",
            "severidad": "MEDIA",
            "detalle": "CCMA menciona 'Crédito por PFP Mis Facilidades' pero Mis Facilidades no listó planes vigentes (verificar paginación o planes cancelados)."
        })

    # Invariante 5: Cuadre por plan en Mis Facilidades (capital_pagado + capital_remanente == consolidado_original)
    for pl in mf.get("planes_vigentes", []):
        orig = float(pl.get("consolidado_original") or 0.0)
        pag = float(pl.get("capital_pagado") or 0.0)
        rem = float(pl.get("capital_remanente") or 0.0)
        if orig > 0 and abs(orig - (pag + rem)) > tolerancia_pesos:
            alertas.append({
                "codigo": "INV_PLAN_CAPITAL_DESCUADRE",
                "severidad": "MEDIA",
                "detalle": f"Plan {pl.get('numero')}: pagado (${pag:,.2f}) + remanente (${rem:,.2f}) != consolidado (${orig:,.2f})."
            })

    # Invariante 6: Cuadre Portal Monotributo (facturado + margen == tope cuando facturado <= tope)
    fact = float(mono.get("facturado_acumulado") or 0.0)
    tope = float(mono.get("tope_categoria") or 0.0)
    marg = float(mono.get("margen_disponible_categoria") or 0.0)
    if tope > 0 and fact <= tope and abs((fact + marg) - tope) > tolerancia_pesos:
        alertas.append({
            "codigo": "INV_MONO_MARGEN_DESCUADRE",
            "severidad": "BAJA",
            "detalle": f"Facturado (${fact:,.2f}) + Margen (${marg:,.2f}) != Tope (${tope:,.2f})."
        })

    if alertas:
        registrar_incidente_calidad("auditoria_unificada", alertas, {"cuits_count": len(resultado.get("cuits_representadas_en_arca") or [])})

    return {
        "invariantes_ok": len(alertas) == 0,
        "controles_ejecutados": 6,
        "alertas_calidad": alertas,
    }
