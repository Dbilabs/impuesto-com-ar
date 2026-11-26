"""
bot/doublecheck_arca.py
Motor de Doble Verificación (Double-Check) y Prohibición de Falsos Negativos en ARCA.

Regla arquitectónica central de impuesto.com.ar:
Ningún agente (Claude, ChatGPT ni el bot local) puede afirmar "Deuda $0", "Al día"
o "Sin presentaciones" sin haber verificado TODAS las fuentes obligatorias del dominio
tributario consultado. Si falta una fuente o dio error/timeout, el veredicto debe ser
explícitamente "VERIFICACIÓN INCOMPLETA" enumerando qué fuentes faltan revisar.
"""

import os
import json
from typing import Dict, Any, List, Optional

MANUALES_INDEX = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "manuales_arca", "indice_guias_arca.json")
)

MATRIZ_DOUBLECHECK_ARCA: Dict[str, Dict[str, Any]] = {
    "estado_de_cuenta_y_deudas": {
        "nombre": "Estado de Cuenta y Deuda Integral",
        "por_que_falla_una_sola_fuente": (
            "SCT > Estado de Cumplimiento solo muestra impuestos generales DGI en una ventana "
            "de 1 año. NO muestra deudas de Monotributo ni Autónomos (viven en CCMA), y cuando "
            "una deuda se consolida en un Plan de Pagos (Mis Facilidades), tanto SCT como CCMA "
            "acreditan 'Crédito por PFP Mis Facilidades' y dejan el saldo en $0,00 ocultando "
            "millones en cuotas vigentes."
        ),
        "fuentes_obligatorias": [
            {
                "id": "ccma",
                "servicio": "CCMA (Cuenta Corriente de Monotributistas y Autónomos)",
                "accion": "Ejecutar 'Cálculo de Deuda' (capital + intereses resarcitorios de Imp. 020, 021, 024 y AUT).",
                "trampa_conocida": "Las cuotas incluidas en planes aparecen en $0 con leyenda 'Crédito por PFP Mis Facilidades Nro ...' — eso obliga a revisar Mis Facilidades."
            },
            {
                "id": "mis_facilidades",
                "servicio": "Mis Facilidades (Seguimiento de Presentación)",
                "accion": "Seleccionar CUIT exacto en <select> y listar TODOS los planes Vigentes y Caducos (número, régimen, cuotas, monto consolidado).",
                "trampa_conocida": "El selector de CUIT es un <select> que puede listar varias CUITs representadas; seleccionar siempre por valor/texto exacto."
            },
            {
                "id": "sct",
                "servicio": "Sistema de Cuentas Tributarias (SCT)",
                "accion": "Seleccionar CUIT exacto por label -> revisar Estado de Cumplimiento (múltiples años si corresponde), Detalle de Deuda Consolidada y Detalle de Incumplimientos.",
                "trampa_conocida": "Estado de Cumplimiento rechaza rangos mayores a 1 año (formato AAAAMM00) y omite Monotributo/Autónomos."
            },
            {
                "id": "portal_monotributo",
                "servicio": "Portal Monotributo (admin_mono)",
                "accion": "Revisar 'Estado de Cuenta', cuotas vencidas del mes en curso y facturación acumulada vs. tope de categoría.",
                "trampa_conocida": "Los pagos recientes pueden demorar 48-72h en reflejarse."
            }
        ],
        "fuentes_fuera_de_arca_alerta_obligatoria": [
            "Ingresos Brutos Provinciales (AGIP CABA / ARBA PBA / Convenio Multilateral SIFERE)",
            "Tasas Municipales (TISH, ABL, Patentes)",
            "Deudas en Gestión Judicial / Boletas de Deuda (Radicación de Juicios)"
        ],
        "palabras_clave": ["deuda", "debo", "estado de cuenta", "saldo", "plan", "facilidades", "ccma", "sct", "autonomos", "monotributo", "moratoria", "cuotas"]
    },
    "ganancias_personas_humanas": {
        "nombre": "Impuesto a las Ganancias Personas Humanas",
        "por_que_falla_una_sola_fuente": (
            "Desde el período fiscal 2025 conviven dos aplicativos independientes: el régimen "
            "general (F. 711) y la Declaración Jurada Simplificada (F. 2711 - RG 5692). Si el "
            "contribuyente presentó por F. 2711, el portal de F. 711 sigue mostrando el período "
            "como 'pendiente/vencido', generando un falso positivo de incumplimiento."
        ),
        "fuentes_obligatorias": [
            {
                "id": "f711",
                "servicio": "Ganancias PH — Declaración Jurada General (F. 711)",
                "accion": "Navegar a #/declaraciones.anteriores y verificar cada período y su saldo determinado.",
                "trampa_conocida": "En #/inicio muestra vencimientos de F. 711 aunque el año ya esté presentado en F. 2711."
            },
            {
                "id": "f2711_simplificada",
                "servicio": "Ganancias PH — Declaración Jurada Simplificada (F. 2711 - RG 5692)",
                "accion": "Ingresar a 'Declaraciones juradas presentadas' (#/declaracion.presentadas) y verificar 'Ratificación anual'.",
                "trampa_conocida": "Los importes en Determinación del Saldo viven en atributos .value de <input>, no en innerText."
            },
            {
                "id": "sct_imp11",
                "servicio": "SCT — Impuesto 11 (Ganancias Personas Físicas)",
                "accion": "Verificar que el Saldo de Libre Disponibilidad (SLD) declarado coincida por período de origen (2024 vs 2025).",
                "trampa_conocida": "Cada período muestra su SLD de origen; el arrastre acumulado no siempre aparece unificado en el último año."
            }
        ],
        "fuentes_fuera_de_arca_alerta_obligatoria": [
            "SiRADIG Trabajador (deducciones informadas al empleador)",
            "Comprobantes de gastos deducibles no informados automáticamente"
        ],
        "palabras_clave": ["ganancias", "711", "2711", "simplificada", "siradig", "rentas", "deducciones"]
    },
    "bienes_personales": {
        "nombre": "Impuesto sobre los Bienes Personales",
        "por_que_falla_una_sola_fuente": (
            "La pantalla inicial (#/inicio) de Bienes Personales Web (F. 762) solo muestra borradores "
            "del período vigente y puede parecer vacía aunque existan 10+ declaraciones históricas."
        ),
        "fuentes_obligatorias": [
            {
                "id": "f762_anteriores",
                "servicio": "Bienes Personales Web (F. 762) — #/declaraciones.anteriores",
                "accion": "Consultar SIEMPRE #/declaraciones.anteriores y abrir el detalle de la última DDJJ presentada.",
                "trampa_conocida": "Nunca concluir 'sin presentaciones' mirando #/inicio."
            },
            {
                "id": "nuestra_parte",
                "servicio": "Nuestra Parte (al 31/12 del año auditado)",
                "accion": "Cruzar inmuebles, rodados, cuentas bancarias, títulos, fideicomisos y tenencias declaradas por terceros.",
                "trampa_conocida": "Puede omitir efectivo en caja/colchón o cuentas del exterior no alcanzadas por CRS."
            },
            {
                "id": "sct_imp180",
                "servicio": "SCT — Impuesto 180 (Bienes Personales)",
                "accion": "Verificar anticipos, pagos, REIBP si aplicó, y saldos a favor o deuda.",
                "trampa_conocida": "Verificar adherentes al REIBP (Ley 27.743) que gozan de estabilidad fiscal."
            }
        ],
        "fuentes_fuera_de_arca_alerta_obligatoria": [
            "Valuaciones fiscales municipales/provinciales (VIR CABA / Valuación Fiscal ARBA) y cotizaciones BNA al 31/12"
        ],
        "palabras_clave": ["bienes personales", "bbpp", "762", "patrimonio", "reibp", "inmuebles"]
    },
    "iva_y_facturacion": {
        "nombre": "IVA, Facturación y Proveedores",
        "por_que_falla_una_sola_fuente": (
            "Mirar solo Mis Comprobantes sin cruzar con Libro IVA Digital, Mis Retenciones y Base e-APOC "
            "puede omitir retenciones/percepciones computables o facturas de proveedores apócrifos impugnables."
        ),
        "fuentes_obligatorias": [
            {"id": "mis_comprobantes", "servicio": "Mis Comprobantes (Emitidos y Recibidos)", "accion": "Descargar ventas y compras del período.", "trampa_conocida": "Verificar comprobantes en moneda extranjera y notas de crédito."},
            {"id": "mis_retenciones", "servicio": "Mis Retenciones (SIRE / SICORE)", "accion": "Consultar retenciones y percepciones de IVA/Ganancias sufridas.", "trampa_conocida": "No confundir retenciones de IIBB provinciales con retenciones nacionales."},
            {"id": "base_eapoc", "servicio": "Base e-APOC (Facturas Apócrifas)", "accion": "Validar CUITs de proveedores relevantes antes de computar crédito fiscal.", "trampa_conocida": "Un proveedor apócrifo impugna crédito fiscal de IVA y deducción en Ganancias."},
            {"id": "sct_imp30", "servicio": "SCT — Impuesto 30 (IVA)", "accion": "Verificar saldos técnicos, SLD y presentaciones de F. 2002 / Libro IVA Digital.", "trampa_conocida": "El saldo técnico (1er párrafo) NO es compensable con otros impuestos; solo el SLD (2do párrafo)."}
        ],
        "fuentes_fuera_de_arca_alerta_obligatoria": [
            "Extractos bancarios y tarjetas (percepciones bancarias / SIRCREB / SIRTAC)",
            "Ingresos Brutos (Local o Convenio Multilateral SIFERE)"
        ],
        "palabras_clave": ["iva", "facturas", "comprobantes", "retenciones", "apocrifas", "e-apoc", "credito fiscal", "debito fiscal"]
    },
    "empleador_seguridad_social": {
        "nombre": "Empleador y Seguridad Social (F. 931)",
        "por_que_falla_una_sola_fuente": (
            "La deuda de cargas sociales puede estar dividida entre SCT Seguridad Social, Mis Facilidades "
            "Previsionales, Sindicatos y Obra Social/ART (que no figuran en ARCA)."
        ),
        "fuentes_obligatorias": [
            {"id": "declaracion_en_linea", "servicio": "Declaración en Línea (F. 931) / Libro de Sueldos Digital", "accion": "Verificar presentaciones F. 931 mensuales.", "trampa_conocida": "Chequear nómina activa en Simplificación Registral."},
            {"id": "sct_segsoc", "servicio": "SCT — Impuestos 301, 302, 351, 352 (Seguridad Social y Obra Social)", "accion": "Verificar pagos y diferencias de aportes/contribuciones.", "trampa_conocida": "El no depósito de aportes retenidos al empleado genera riesgo penal tributario."},
            {"id": "mis_facilidades_ss", "servicio": "Mis Facilidades (Planes Previsionales)", "accion": "Listar planes vigentes/caducos de aportes y contribuciones.", "trampa_conocida": "La caducidad de un plan reactiva deuda exigible con intereses."}
        ],
        "fuentes_fuera_de_arca_alerta_obligatoria": [
            "Aportes Sindicales y Boletas de Sindicato (fuera de ARCA)",
            "ART y Seguro de Vida Obligatorio"
        ],
        "palabras_clave": ["931", "sueldos", "empleados", "empleador", "cargas sociales", "seguridad social", "aportes"]
    }
}


def detectar_dominio_doublecheck(consulta: str) -> str:
    q = (consulta or "").lower()
    if q in MATRIZ_DOUBLECHECK_ARCA:
        return q
    best_dom = "estado_de_cuenta_y_deudas"
    best_score = 0
    for dom, cfg in MATRIZ_DOUBLECHECK_ARCA.items():
        score = sum(1 for kw in cfg["palabras_clave"] if kw in q)
        if score > best_score:
            best_score = score
            best_dom = dom
    return best_dom


def buscar_manuales_relacionados(dominio: str, limite: int = 5) -> List[Dict[str, Any]]:
    if not os.path.exists(MANUALES_INDEX):
        return []
    try:
        with open(MANUALES_INDEX, "r", encoding="utf-8") as f:
            guias = json.load(f)
        kws = MATRIZ_DOUBLECHECK_ARCA.get(dominio, {}).get("palabras_clave", [])
        hits = []
        for g in guias:
            txt = (str(g.get("titulo", "")) + " " + str(g.get("categoria", "")) + " " + str(g.get("url", ""))).lower()
            if any(k in txt for k in kws):
                hits.append({
                    "titulo": g.get("titulo"),
                    "categoria": g.get("categoria"),
                    "url": g.get("url")
                })
                if len(hits) >= limite:
                    break
        return hits
    except Exception:
        return []


def obtener_protocolo_doublecheck(consulta_o_dominio: str) -> Dict[str, Any]:
    """
    Devuelve la lista obligatoria de fuentes ARCA que DEBEN verificarse antes de emitir
    cualquier conclusión de deuda, saldo o cumplimiento para el dominio consultado.
    """
    dom = detectar_dominio_doublecheck(consulta_o_dominio)
    cfg = MATRIZ_DOUBLECHECK_ARCA[dom]
    return {
        "dominio": dom,
        "nombre": cfg["nombre"],
        "regla_oro": (
            "PROHIBICIÓN DE FALSO NEGATIVO: No emitir jamás 'Deuda $0', 'Al día' ni 'Sin presentaciones' "
            "sin verificar el 100% de las fuentes_obligatorias. Si alguna fuente no se pudo consultar, "
            "informar explícitamente 'VERIFICACIÓN INCOMPLETA' indicando qué falta revisar."
        ),
        "por_que_es_critico": cfg["por_que_falla_una_sola_fuente"],
        "fuentes_obligatorias": cfg["fuentes_obligatorias"],
        "alertas_fuera_de_arca": cfg["fuentes_fuera_de_arca_alerta_obligatoria"],
        "manuales_arca_relacionados": buscar_manuales_relacionados(dom)
    }


def validar_cobertura_auditoria(
    dominio: str,
    fuentes_verificadas: List[str],
    fuentes_fallidas: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Evalúa si el agente completó TODAS las fuentes obligatorias de un dominio.
    Bloquea veredictos de 'Deuda $0' o 'Al día' cuando la cobertura es incompleta.
    """
    dom = detectar_dominio_doublecheck(dominio)
    cfg = MATRIZ_DOUBLECHECK_ARCA[dom]
    obligatorias = [f["id"] for f in cfg["fuentes_obligatorias"]]
    verif_set = {x.strip().lower() for x in (fuentes_verificadas or [])}
    fall_set = {x.strip().lower() for x in (fuentes_fallidas or [])}

    cubiertas = [fid for fid in obligatorias if fid in verif_set]
    faltantes = [fid for fid in obligatorias if fid not in verif_set]
    completa = len(faltantes) == 0 and len(fall_set) == 0

    return {
        "dominio": dom,
        "verificacion_completa": completa,
        "puede_afirmar_deuda_cero_o_al_dia": completa,
        "cobertura": f"{len(cubiertas)}/{len(obligatorias)}",
        "fuentes_verificadas": cubiertas,
        "fuentes_faltantes": faltantes,
        "fuentes_con_error": list(fall_set),
        "sello_verificacion": (
            f"✅ VERIFICACIÓN INTEGRAL ARCA ({len(cubiertas)}/{len(obligatorias)}: {', '.join(cubiertas)}) "
            f"| ⚠️ No incluye tributos fuera de ARCA ({'; '.join(cfg['fuentes_fuera_de_arca_alerta_obligatoria'][:2])})"
            if completa else
            f"⚠️ VERIFICACIÓN INCOMPLETA ({len(cubiertas)}/{len(obligatorias)}) — Faltan revisar: {', '.join(faltantes)}. "
            "PROHIBIDO concluir 'Deuda $0' o 'Al día' hasta completar estas fuentes."
        )
    }
