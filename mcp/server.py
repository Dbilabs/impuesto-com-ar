#!/usr/bin/env python3
"""
ARCA MCP Server (impuesto.com.ar)
Permite a asistentes de Inteligencia Artificial (Claude Desktop, Cursor, ChatGPT, Antigravity)
interactuar de forma segura con ARCA (ex AFIP) para consultar comprobantes, estimar IVA,
leer notificaciones del Domicilio Fiscal Electrónico y gestionar empresas representadas.
"""

import os
import sys
import datetime
from typing import Optional, Dict, Any, List
from mcp.server.fastmcp import FastMCP

# Agregar directorio raíz para importar el bot
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from bot.scraper import (
    consultar_mis_comprobantes,
    consultar_notificaciones_dfe,
    listar_empresas_representadas
)
from bot.scraper_monotributo import (
    consultar_estado_monotributo as _consultar_monotributo,
    generar_plan_de_accion as _generar_plan_accion
)
from bot.facturacion import armar_borrador_factura as _armar_borrador_factura
from bot.recordatorios import calcular_vencimientos_cuit as _calcular_vencimientos, generar_respuesta_arca_caida as _arca_caida
from bot.iva_presentacion import liquidar_iva_periodo as _liquidar_iva
from bot.iibb_sifere import liquidar_iibb_periodo as _liquidar_iibb
from bot.sueldos_f931 import liquidar_sueldo_y_cargas as _liquidar_sueldos
from bot.asesor_fiscal import consultar_asesor as _consultar_asesor
from bot.catalogo_tramites import obtener_catalogo_completo as _obtener_catalogo, ejecutar_tramite as _ejecutar_tramite
from bot.exportacion_dolares import calcular_cupo_dolares_freelancer as _calcular_cupo_dolares
from bot.certificaciones import armar_certificacion_ingresos as _armar_cert_ingresos, armar_certificacion_origen_fondos as _armar_cert_origen
from bot.perfil_fiscal import evaluar_perfil_fiscal as _evaluar_perfil
from bot.novedades_fiscales import (
    obtener_novedades_y_moratorias as _obtener_novedades,
    simular_plan_pago as _simular_plan,
    solicitar_revision_contador_humano as _solicitar_revision
)
from bot.jurisprudencia_fiscal import (
    consultar_jurisprudencia as _consultar_jurisprudencia,
    consultar_politica_provincial_municipal as _consultar_provincial_municipal
)
from bot.manuales_knowledge import buscar_manual_o_guia as _buscar_manual_guia
from bot.documentos_y_visuales import (
    obtener_checklist_documentos_faltantes as _checklist_docs,
    conciliar_y_generar_reporte_visual as _conciliar_y_graficar,
    analizar_impacto_economico_financiero as _analizar_impacto_ef
)
from bot.aprendizaje_continuo import (
    registrar_consulta_sin_respuesta as _registrar_consulta,
    incorporar_conocimiento_resuelto as _incorporar_conocimiento,
    buscar_conocimiento_aprendido as _buscar_aprendido
)
from bot.arca_ws import (
    verificar_estado_servidores_wsfe as _wsfe_dummy,
    generar_csr_arca as _generar_csr,
    emitir_comprobante_wsfe as _emitir_wsfe,
    consultar_padron_a5 as _padron_a5
)
from bot.scraper_bbpp import consultar_bienes_personales_web as _consultar_bbpp_web
from bot.scraper_extras_arca import (
    consultar_ccma as _consultar_ccma,
    consultar_mis_retenciones as _consultar_mis_retenciones,
    consultar_nuestra_parte as _consultar_nuestra_parte,
    verificar_proveedor_apocrifo_apoc as _verificar_apoc,
    consultar_y_renovar_certificado_mipyme as _certificado_mipyme
)
from bot.pdf_factura import generar_factura_html_y_pdf as _generar_pdf_factura
from bot.estudio_contable import (
    configurar_estudio_contable as _configurar_estudio,
    importar_cartera_clientes as _importar_cartera,
    tablero_cartera_estudio as _tablero_cartera,
    registrar_cierre_y_detectar_anomalias as _registrar_cierre,
    aprobar_cierres_socio as _aprobar_cierres,
    generar_reporte_marca_blanca_cliente as _reporte_marca_blanca
)

_PERFILES_CACHE: Dict[str, Dict[str, Any]] = {}

mcp = FastMCP("impuesto-arca-mcp")

def _get_credentials(usuario: Optional[str], clave: Optional[str]):
    u = usuario or os.environ.get("ARCA_CUIT")
    c = clave or os.environ.get("ARCA_CLAVE")
    if not u or not c:
        raise ValueError("Se requieren credenciales de ARCA (usuario/CUIT y clave fiscal) como parámetros o en variables de entorno ARCA_CUIT y ARCA_CLAVE.")
    return u, c

def _parse_periodo(periodo: str) -> str:
    """Convierte '2026-11' o '11/2026' a '01/11/2026 - 30/11/2026'."""
    p = periodo.strip()
    if " - " in p:
        return p
    if "-" in p and len(p) == 7: # YYYY-MM
        y, m = p.split("-")
        mes = int(m)
        anio = int(y)
    elif "/" in p and len(p) == 7: # MM/YYYY
        m, y = p.split("/")
        mes = int(m)
        anio = int(y)
    else:
        now = datetime.datetime.now()
        mes, anio = now.month, now.year

    # Último día del mes aproximado
    if mes in [1, 3, 5, 7, 8, 10, 12]:
        ultimo = 31
    elif mes in [4, 6, 9, 11]:
        ultimo = 30
    else:
        ultimo = 29 if anio % 4 == 0 else 28

    return f"01/{mes:02d}/{anio} - {ultimo:02d}/{anio}"

def _num(v):
    if not v:
        return 0.0
    s = str(v).replace("$", "").replace(" ", "").strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0

@mcp.tool()
def listar_empresas(usuario: Optional[str] = None, clave: Optional[str] = None) -> List[Dict[str, str]]:
    """
    Lista todas las personas físicas y empresas jurídicas que el usuario tiene autorización
    para operar y representar en ARCA (AFIP).
    """
    u, c = _get_credentials(usuario, clave)
    return listar_empresas_representadas(u, c)

@mcp.tool()
def leer_notificaciones_dfe(cuit: Optional[str] = None, usuario: Optional[str] = None, clave: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Consulta la bandeja de comunicaciones oficiales en el Domicilio Fiscal Electrónico (DFE)
    para el CUIT especificado (o para todos los representados si no se especifica CUIT).
    Permite detectar intimaciones, fiscalizaciones y avisos de vencimiento antes de que venza el plazo.
    """
    u, c = _get_credentials(usuario, clave)
    return consultar_notificaciones_dfe(usuario=u, clave=c, cuit_objetivo=cuit)

@mcp.tool()
def consultar_comprobantes_mes(
    cuit: str,
    periodo: str,
    tipo: str = "ambos",
    usuario: Optional[str] = None,
    clave: Optional[str] = None
) -> Dict[str, Any]:
    """
    Consulta los comprobantes emitidos y/o recibidos en ARCA ('Mis Comprobantes') para un CUIT y período ('YYYY-MM').
    Calcula el Débito Fiscal total (IVA Ventas), Crédito Fiscal total (IVA Compras),
    el IVA Determinado preliminar a pagar y el resumen de principales clientes y proveedores.
    """
    u, c = _get_credentials(usuario, clave)
    rango = _parse_periodo(periodo)

    emitidos = []
    recibidos = []

    if tipo in ["emitidos", "ambos"]:
        emitidos = consultar_mis_comprobantes(cuit=cuit, usuario=u, clave=c, tipo="E", rango_fechas=rango)

    if tipo in ["recibidos", "ambos"]:
        recibidos = consultar_mis_comprobantes(cuit=cuit, usuario=u, clave=c, tipo="R", rango_fechas=rango)

    # Calcular totales
    debito_fiscal = sum(_num(r.get("Total IVA", 0)) for r in emitidos)
    credito_fiscal = sum(_num(r.get("Total IVA", 0)) for r in recibidos)
    total_ventas = sum(_num(r.get("Imp. Total", 0)) for r in emitidos)
    total_compras = sum(_num(r.get("Imp. Total", 0)) for r in recibidos)

    top_proveedores = {}
    for r in recibidos:
        emisor = r.get("Denominación Emisor", "Desconocido")
        top_proveedores[emisor] = top_proveedores.get(emisor, 0.0) + _num(r.get("Imp. Total", 0))

    top_clientes = {}
    for r in emitidos:
        receptor = r.get("Denominación Receptor", "Desconocido")
        top_clientes[receptor] = top_clientes.get(receptor, 0.0) + _num(r.get("Imp. Total", 0))

    return {
        "cuit": cuit,
        "periodo": periodo,
        "rango_fechas": rango,
        "resumen_iva": {
            "debito_fiscal": round(debito_fiscal, 2),
            "credito_fiscal": round(credito_fiscal, 2),
            "iva_determinado": round(debito_fiscal - credito_fiscal, 2),
            "estado": "A pagar" if debito_fiscal > credito_fiscal else "Saldo a favor técnico"
        },
        "totales_facturacion": {
            "total_ventas_brutas": round(total_ventas, 2),
            "cantidad_emitidos": len(emitidos),
            "total_compras_brutas": round(total_compras, 2),
            "cantidad_recibidos": len(recibidos)
        },
        "top_proveedores": sorted([{"nombre": k, "monto": round(v, 2)} for k, v in top_proveedores.items()], key=lambda x: x["monto"], reverse=True)[:5],
        "top_clientes": sorted([{"nombre": k, "monto": round(v, 2)} for k, v in top_clientes.items()], key=lambda x: x["monto"], reverse=True)[:5],
        "comprobantes_emitidos_detalle": emitidos[:10],
        "comprobantes_recibidos_detalle": recibidos[:10]
    }

@mcp.tool()
def consultar_situacion_monotributo(
    usuario: Optional[str] = None,
    clave: Optional[str] = None
) -> Dict[str, Any]:
    """
    Ingresa al portal de MONOTRIBUTO de ARCA en vivo y extrae la categoría actual,
    tipo de actividad, facturación acumulada 12 meses, tope de categoría, margen disponible,
    próxima recategorización y períodos impagos.
    """
    u, c = _get_credentials(usuario, clave)
    estado = _consultar_monotributo(u, c)
    plan = _generar_plan_accion(estado)
    return {
        "estado": estado,
        "plan_de_accion": plan
    }

@mcp.tool()
def preparar_factura_empresa(
    emisor_cuit: str,
    emisor_razon_social: str,
    emisor_condicion: str,
    receptor_cuit: str,
    receptor_razon_social: str,
    receptor_condicion: str,
    items: List[Dict[str, Any]],
    receptor_domicilio: str = "Ciudad de Buenos Aires",
    punto_venta: int = 1,
    concepto: str = "Servicios",
    forma_pago: str = "Transferencia Bancaria",
    cbu_cobranza: Optional[str] = None
) -> Dict[str, Any]:
    """
    Prepara un borrador fiscal verificado de factura (A, B, C o E) para Empresas o Monotributistas.
    Determina automáticamente la letra, discrimina o integra las alícuotas de IVA (21%, 10.5%, 27%),
    calcula subtotales y muestra el impacto directo en el Libro de IVA Digital y F. 2002.
    """
    return _armar_borrador_factura(
        emisor_cuit=emisor_cuit,
        emisor_razon_social=emisor_razon_social,
        emisor_condicion=emisor_condicion,
        receptor_cuit=receptor_cuit,
        receptor_razon_social=receptor_razon_social,
        receptor_condicion=receptor_condicion,
        receptor_domicilio=receptor_domicilio,
        items=items,
        punto_venta=punto_venta,
        concepto=concepto,
        forma_pago=forma_pago,
        cbu_cobranza=cbu_cobranza
    )

@mcp.tool()
def obtener_recordatorios_fiscales(
    cuit: str,
    regimen: str = "auto"
) -> Dict[str, Any]:
    """
    Calcula el calendario de vencimientos oficiales de ARCA personalizados para el CUIT
    (según último dígito) y régimen (Monotributo, Responsable Inscripto o Empleador),
    generando los prompts de recordatorio predeterminados para agendar en la IA.
    """
    return _calcular_vencimientos(cuit=cuit, regimen=regimen)

@mcp.tool()
def liquidar_iva_mensual(
    cuit: str,
    periodo: str,
    ventas: List[Dict[str, Any]],
    compras: List[Dict[str, Any]],
    retenciones_bancarias: float = 0.0,
    percepciones_sufridas: float = 0.0,
    saldo_tecnico_anterior: float = 0.0,
    saldo_libre_disponibilidad_anterior: float = 0.0
) -> Dict[str, Any]:
    """
    Liquida la posición mensual de IVA con la metodología oficial del F. 2002 de ARCA,
    prepara el Libro de IVA Digital (RG 4597) y explica el resultado en lenguaje ultra sencillo.
    """
    return _liquidar_iva(
        cuit=cuit,
        periodo=periodo,
        ventas=ventas,
        compras=compras,
        retenciones_bancarias=retenciones_bancarias,
        percepciones_sufridas=percepciones_sufridas,
        saldo_tecnico_anterior=saldo_tecnico_anterior,
        saldo_libre_disponibilidad_anterior=saldo_libre_disponibilidad_anterior
    )

@mcp.tool()
def liquidar_ingresos_brutos(
    cuit: str,
    periodo: str,
    jurisdiccion: str,
    facturacion_bruta: float,
    alicuota: float = 0.03,
    retenciones_bancarias_sircreb: float = 0.0,
    percepciones_sufridas: float = 0.0,
    saldo_a_favor_anterior: float = 0.0
) -> Dict[str, Any]:
    """
    Liquida Ingresos Brutos mensual (CABA/AGIP, PBA/ARBA o Convenio Multilateral CM03),
    audita deducciones bancarias y detecta si el SIRCREB te está reteniendo plata de más.
    """
    return _liquidar_iibb(
        cuit=cuit,
        periodo=periodo,
        jurisdiccion=jurisdiccion,
        facturacion_bruta=facturacion_bruta,
        alicuota=alicuota,
        retenciones_bancarias_sircreb=retenciones_bancarias_sircreb,
        percepciones_sufridas=percepciones_sufridas,
        saldo_a_favor_anterior=saldo_a_favor_anterior
    )

@mcp.tool()
def calcular_sueldo_y_cargas(
    sueldo_bruto: float,
    tipo_empleador: str = "servicios"
) -> Dict[str, Any]:
    """
    Calcula el recibo de sueldo neto en mano del empleado, los aportes retenidos (17%)
    y las contribuciones patronales para el Formulario 931 y Libro de Sueldos Digital.
    """
    return _liquidar_sueldos(sueldo_bruto=sueldo_bruto, tipo_empleador=tipo_empleador)

@mcp.tool()
def consultar_asesor_tributario(
    tema: str
) -> Dict[str, Any]:
    """
    Asesor impositivo senior de Argentina. Responde consultas complejas sobre deducciones,
    Monotributo vs SRL, dividendos y defensas de ARCA, con analogías sencillas ('para un chico de 10 años')
    y citas técnicas a las leyes y artículos vigentes.
    """
    return _consultar_asesor(tema=tema)

@mcp.tool()
def consultar_catalogo_tramites(
    categoria: Optional[str] = None
) -> Dict[str, Any]:
    """
    Consulta el catálogo de más de 80 trámites automatizables en ARCA, Rentas y BCRA
    (Monotributo, Facturación, IVA, IIBB, Ganancias, Sueldos, Sociedades, Certificaciones).
    """
    return _obtener_catalogo(categoria=categoria)

@mcp.tool()
def ejecutar_tramite_arca(
    tramite_id: str,
    cuit: str,
    parametros: Dict[str, Any],
    confirmado: bool = False
) -> Dict[str, Any]:
    """
    Ejecuta o simula cualquiera de los 80 trámites de ARCA mediante el motor de bots.
    Requiere confirmado=True para impactar en ARCA.
    """
    return _ejecutar_tramite(tramite_id=tramite_id, cuit=cuit, parametros=parametros, confirmado=confirmado)

@mcp.tool()
def calcular_cupo_dolares_freelancer(
    cuit: str,
    dolares_ingresados_anio: float,
    nuevo_cobro_usd: float,
    cotizacion_oficial_bna: float = 1045.0
) -> Dict[str, Any]:
    """
    Calcula el cupo restante de USD 24.000 anuales del BCRA para exportadores de servicios
    libres de pesificación forzosa en MULC y prepara la liquidación bancaria.
    """
    return _calcular_cupo_dolares(
        cuit=cuit,
        dolares_ingresados_anio=dolares_ingresados_anio,
        nuevo_cobro_usd=nuevo_cobro_usd,
        cotizacion_oficial_bna=cotizacion_oficial_bna
    )

@mcp.tool()
def armar_certificacion_ingresos(
    cuit: str,
    contribuyente_nombre: str,
    actividad: str,
    ingresos_mensuales: List[Dict[str, Any]],
    periodo_meses: int = 6,
    destinatario: str = "A quien corresponda"
) -> Dict[str, Any]:
    """
    Genera la minuta de Certificación de Ingresos para alquileres o créditos bancarios
    conforme a normas del CPCECABA/CPCEPBA.
    """
    return _armar_cert_ingresos(
        cuit=cuit,
        contribuyente_nombre=contribuyente_nombre,
        actividad=actividad,
        periodo_meses=periodo_meses,
        ingresos_mensuales=ingresos_mensuales,
        destinatario=destinatario
    )

@mcp.tool()
def armar_certificacion_origen_fondos(
    cuit: str,
    contribuyente_nombre: str,
    monto_operacion: float,
    bien_a_adquirir: str,
    fuentes_justificacion: List[Dict[str, Any]],
    destinatario: str = "Escribanía / Registro Automotor"
) -> Dict[str, Any]:
    """
    Genera la Certificación de Origen Lícito de Fondos requerida por normas de la UIF
    para compra de inmuebles, automotores o inversiones.
    """
    return _armar_cert_origen(
        cuit=cuit,
        contribuyente_nombre=contribuyente_nombre,
        monto_operacion=monto_operacion,
        bien_a_adquirir=bien_a_adquirir,
        fuentes_justificacion=fuentes_justificacion,
        destinatario=destinatario
    )

@mcp.tool()
def configurar_perfil_contribuyente(
    cuit: str,
    tipo_personeria: str,
    que_vende: str,
    a_quien_vende: str,
    ubicacion_sede: str,
    jurisdicciones_operacion: Optional[List[str]] = None,
    cantidad_empleados: int = 0,
    rol: Optional[str] = None,
    razon_social: Optional[str] = None,
    convenio_colectivo: Optional[str] = None
) -> Dict[str, Any]:
    """
    Registra el perfil base de negocio del cliente para que la IA entienda su marco fiscal exacto:
    rol, qué vende, a quién le vende, dónde está ubicado, provincias donde opera y cantidad de empleados.
    Determina automáticamente qué facturas emitir (A, B, C, E), si aplica Convenio Multilateral (SIFERE)
    o régimen local de IIBB, si corresponde F. 931 de nómina y emite recomendaciones a medida.
    """
    res = _evaluar_perfil(
        cuit=cuit,
        tipo_personeria=tipo_personeria,
        que_vende=que_vende,
        a_quien_vende=a_quien_vende,
        ubicacion_sede=ubicacion_sede,
        jurisdicciones_operacion=jurisdicciones_operacion,
        cantidad_empleados=cantidad_empleados,
        rol=rol,
        razon_social=razon_social,
        convenio_colectivo=convenio_colectivo
    )
    cuit_clean = "".join([c for c in str(cuit) if c.isdigit()])
    _PERFILES_CACHE[cuit_clean] = res
    return res

@mcp.tool()
def obtener_perfil_contribuyente(cuit: str) -> Dict[str, Any]:
    """
    Recupera el perfil operativo y marco fiscal previamente registrado para un CUIT.
    """
    cuit_clean = "".join([c for c in str(cuit) if c.isdigit()])
    if cuit_clean in _PERFILES_CACHE:
        return _PERFILES_CACHE[cuit_clean]
    return {
        "cuit": cuit_clean,
        "registrado": False,
        "mensaje": "No hay un perfil de negocio registrado para este CUIT. Por favor llama a configurar_perfil_contribuyente con los 5 datos básicos (rol, qué vende, a quién vende, ubicación y empleados)."
    }

@mcp.tool()
def consultar_novedades_y_moratorias(
    categoria: Optional[str] = None
) -> Dict[str, Any]:
    """
    Informa sobre moratorias vigentes (Ley 27.743), blanqueo de activos (Régimen de Regularización),
    planes de pago de ARCA y novedades tributarias diarias, explicadas en lenguaje simple y con citas legales.
    """
    return _obtener_novedades(categoria=categoria)

@mcp.tool()
def simular_plan_pago_deuda(
    deuda_total: float,
    cantidad_cuotas: int = 12,
    tipo_contribuyente: str = "monotributo"
) -> Dict[str, Any]:
    """
    Calcula la simulación de cuotas, pago a cuenta, interés mensual y débito automático CBU
    para regularizar deudas fiscales en planes de facilidades de pago de ARCA.
    """
    return _simular_plan(
        deuda_total=deuda_total,
        cantidad_cuotas=cantidad_cuotas,
        tipo_contribuyente=tipo_contribuyente
    )

@mcp.tool()
def solicitar_revision_contador_humano(
    cuit: str,
    tema_o_tramite: str,
    contacto_usuario: Optional[str] = None
) -> Dict[str, Any]:
    """
    Garantía Human-in-the-Loop: solicita que un Contador Público Matriculado humano revise,
    audite y valide cualquier cálculo, borrador o trámite generado por la IA antes de confirmarlo.
    """
    return _solicitar_revision(
        cuit=cuit,
        tema_o_tramite=tema_o_tramite,
        contacto_usuario=contacto_usuario
    )

@mcp.tool()
def consultar_jurisprudencia_fiscal(
    tema_o_conflicto: str
) -> Dict[str, Any]:
    """
    Consulta los fallos líderes de la Corte Suprema (CSJN), Tribunal Fiscal y Comisión Arbitral
    (Esso c/ Quilmes, Candy c/ AFIP, Laboratorios Raffo, Bayer c/ Santa Fe, Intercorp)
    para fundamentar defensas legales y contables contra abusos fiscales y confiscatoriedad.
    """
    return _consultar_jurisprudencia(tema_o_conflicto=tema_o_conflicto)

@mcp.tool()
def consultar_tasas_provinciales_municipales(
    jurisdiccion: str,
    municipio: Optional[str] = None,
    rubro: Optional[str] = None
) -> Dict[str, Any]:
    """
    Informa las políticas fiscales provinciales (alícuotas de Ingresos Brutos y Sellos en CABA, PBA, Córdoba, Santa Fe, Mendoza)
    y tasas municipales (Tasa de Seguridad e Higiene, Tasa Vial), evaluando el sustento territorial para frenar cobros abusivos.
    """
    return _consultar_provincial_municipal(
        jurisdiccion=jurisdiccion,
        municipio=municipio,
        rubro=rubro
    )

@mcp.tool()
def consultar_manuales_y_guias_arca(
    query: str,
    categoria: Optional[str] = None
) -> Dict[str, Any]:
    """
    Accede a la base de conocimiento de 245 guías paso a paso oficiales, manuales de usuario
    y arquitectura de rutas internas de ARCA (incluyendo SPA AngularJS, solapas de historiales
    y aplicativos legados del SiAP para entender la lógica de fondo de cada trámite).
    """
    return _buscar_manual_guia(query=query, categoria=categoria)

@mcp.tool()
def solicitar_documentos_complementarios(
    tramite: str,
    tipo_personeria: str = "empresa"
) -> Dict[str, Any]:
    """
    Genera el checklist exacto de documentos 'off-ARCA' que el cliente debe adjuntar en el chat
    del LLM (extractos bancarios, resúmenes de tarjetas de crédito, pólizas de seguros, invoices
    del exterior, novedades de empleados) para armar la película fiscal completa.
    """
    return _checklist_docs(tramite=tramite, tipo_personeria=tipo_personeria)

@mcp.tool()
def conciliar_y_graficar_pelicula_fiscal(
    facturacion_bruta: float,
    gastos_arca: float = 0.0,
    gastos_adjuntos_off_arca: float = 0.0,
    retenciones_sircreb_banco: float = 0.0,
    impuesto_cheque_computable: float = 0.0,
    percepciones_tarjeta_recuperables: float = 0.0,
    acreditaciones_bancarias_mes: float = 0.0,
    iva_estimado: float = 0.0,
    iibb_estimado: float = 0.0,
    ganancias_o_cuota_estimada: float = 0.0,
    tope_categoria_anual: Optional[float] = None,
    facturacion_acumulada_12m: Optional[float] = None
) -> Dict[str, Any]:
    """
    Concilia los datos de ARCA con los comprobantes adjuntados por el cliente en el LLM (bancos,
    tarjetas, seguros, gastos no registrados), calcula el ahorro fiscal rescatado, alerta descalces
    bancarios y devuelve gráficos listos para renderizar (Mermaid pie/bar + semáforo de tope).
    """
    return _conciliar_y_graficar(
        facturacion_bruta=facturacion_bruta,
        gastos_arca=gastos_arca,
        gastos_adjuntos_off_arca=gastos_adjuntos_off_arca,
        retenciones_sircreb_banco=retenciones_sircreb_banco,
        impuesto_cheque_computable=impuesto_cheque_computable,
        percepciones_tarjeta_recuperables=percepciones_tarjeta_recuperables,
        acreditaciones_bancarias_mes=acreditaciones_bancarias_mes,
        iva_estimado=iva_estimado,
        iibb_estimado=iibb_estimado,
        ganancias_o_cuota_estimada=ganancias_o_cuota_estimada,
        tope_categoria_anual=tope_categoria_anual,
        facturacion_acumulada_12m=facturacion_acumulada_12m
    )

@mcp.tool()
def registrar_consulta_sin_respuesta(
    pregunta: str,
    cuit_origen: Optional[str] = None,
    contexto_cliente: Optional[str] = None
) -> Dict[str, Any]:
    """
    Agenda una pregunta del cliente para la cual el bot no tiene una respuesta validada.
    Evita improvisar: deriva la duda a un especialista humano y, al resolverse, se incorpora
    automáticamente al conocimiento permanente del bot.
    """
    return _registrar_consulta(
        pregunta=pregunta,
        cuit_origen=cuit_origen,
        contexto_cliente=contexto_cliente
    )

@mcp.tool()
def incorporar_conocimiento_resuelto(
    consulta_id: str,
    respuesta_clara: str,
    normativa_oficial: str = ""
) -> Dict[str, Any]:
    """
    Cierra una consulta previamente agendada y suma la respuesta validada a la base de
    conocimiento permanente del bot para responder automáticamente a futuros clientes.
    """
    return _incorporar_conocimiento(
        consulta_id=consulta_id,
        respuesta_clara=respuesta_clara,
        normativa_oficial=normativa_oficial
    )

@mcp.tool()
def buscar_conocimiento_aprendido(query: str) -> Dict[str, Any]:
    """
    Busca respuestas previamente resueltas por contadores especialistas e incorporadas
    a la memoria viva del bot a partir de casos reales de clientes.
    """
    return _buscar_aprendido(query=query)

@mcp.tool()
def analizar_impacto_economico_financiero(
    ventas_formales_mes: float,
    ventas_informales_mes: float = 0.0,
    compras_formales_mes: float = 0.0,
    compras_informales_mes: float = 0.0,
    empleados_registrados: int = 0,
    empleados_no_registrados: int = 0,
    sueldo_promedio_bruto: float = 950000.0,
    cobra_informal_por_banco_o_mp: bool = False
) -> Dict[str, Any]:
    """
    Analiza la fotografía económico-financiera real del negocio (circuito formal + informal)
    para medir rentabilidad verdadera, cuantificar contingencias laborales y bancarias (Art. 18
    Ley 11.683) y proponer acciones concretas de ordenamiento, regularización laboral (Ley Bases)
    y beneficios MiPyME que protejan la caja.
    """
    return _analizar_impacto_ef(
        ventas_formales_mes=ventas_formales_mes,
        ventas_informales_mes=ventas_informales_mes,
        compras_formales_mes=compras_formales_mes,
        compras_informales_mes=compras_informales_mes,
        empleados_registrados=empleados_registrados,
        empleados_no_registrados=empleados_no_registrados,
        sueldo_promedio_bruto=sueldo_promedio_bruto,
        cobra_informal_por_banco_o_mp=cobra_informal_por_banco_o_mp
    )

@mcp.tool()
def verificar_estado_servidores_arca_ws(ambiente: str = "produccion") -> Dict[str, Any]:
    """
    Ejecuta FEDummy en vivo contra los Web Services oficiales WSFEv1 de ARCA (producción u homologación)
    para comprobar en <1 segundo si AppServer, DbServer y AuthServer están operativos.
    """
    return _wsfe_dummy(ambiente=ambiente)

@mcp.tool()
def generar_certificado_csr_arca(
    cuit: str,
    razon_social: str,
    alias: str = "impuesto_mcp"
) -> Dict[str, Any]:
    """
    Genera clave privada RSA 2048 y archivo .csr compatible con ARCA para vincular los Web Services
    oficiales (WSFEv1 y Padrón A5) en 'Administración de Certificados Digitales'.
    """
    return _generar_csr(cuit=cuit, razon_social=razon_social, alias=alias)

@mcp.tool()
def emitir_factura_wsfe(
    cuit_emisor: str,
    pto_vta: int,
    cbte_tipo: int,
    receptor_cuit: str,
    importe_neto: float,
    importe_iva: float = 0.0,
    concepto: int = 2,
    ambiente: str = "homologacion",
    confirmado: bool = False
) -> Dict[str, Any]:
    """
    Prepara o emite una factura electrónica oficial (A=1, B=6, C=11) vía Web Service WSFEv1 de ARCA
    con CAE y URL de Código QR oficial en <1 segundo. Requiere confirmado=True para impactar en ARCA.
    """
    return _emitir_wsfe(
        cuit_emisor=cuit_emisor,
        pto_vta=pto_vta,
        cbte_tipo=cbte_tipo,
        receptor_cuit=receptor_cuit,
        importe_neto=importe_neto,
        importe_iva=importe_iva,
        concepto=concepto,
        ambiente=ambiente,
        confirmado=confirmado
    )

@mcp.tool()
def consultar_padron_cuit_ws(
    cuit_consulta: str,
    cuit_representado: Optional[str] = None,
    ambiente: str = "produccion"
) -> Dict[str, Any]:
    """
    Consulta la constancia de inscripción (Razón Social, condición IVA/Monotributo, domicilio fiscal
    y actividad principal) de cualquier CUIT vía Web Service WS_SR_PADRON_A5 en <1 segundo.
    """
    return _padron_a5(
        cuit_consulta=cuit_consulta,
        cuit_representado=cuit_representado,
        ambiente=ambiente
    )

@mcp.tool()
def consultar_bienes_personales_web(usuario: Optional[str] = None, clave: Optional[str] = None) -> Dict[str, Any]:
    """
    Ingresa a BIENES PERSONALES WEB (F. 762) navegando obligatoriamente #/declaraciones.anteriores
    para extraer el historial real completo de DDJJ presentadas y el próximo vencimiento anual.
    """
    u, c = _get_credentials(usuario, clave)
    return _consultar_bbpp_web(usuario=u, clave=c)

@mcp.tool()
def consultar_ccma_cuenta_corriente(usuario: Optional[str] = None, clave: Optional[str] = None) -> Dict[str, Any]:
    """
    Consulta CCMA (Cuenta Corriente de Monotributistas y Autónomos) en ARCA: extrae saldo deudor,
    intereses resarcitorios y saldo acreedor a favor.
    """
    u, c = _get_credentials(usuario, clave)
    return _consultar_ccma(usuario=u, clave=c)

@mcp.tool()
def consultar_mis_retenciones_arca(
    cuit_objetivo: Optional[str] = None,
    usuario: Optional[str] = None,
    clave: Optional[str] = None
) -> Dict[str, Any]:
    """
    Consulta el servicio MIS RETENCIONES (SIRE/SICORE) en ARCA para relevar retenciones y
    percepciones de IVA/Ganancias computables a favor del contribuyente.
    """
    u, c = _get_credentials(usuario, clave)
    return _consultar_mis_retenciones(usuario=u, clave=c, cuit_objetivo=cuit_objetivo)

@mcp.tool()
def consultar_nuestra_parte_arca(usuario: Optional[str] = None, clave: Optional[str] = None) -> Dict[str, Any]:
    """
    Consulta 'Nuestra Parte' en ARCA para ver exactamente qué inmuebles, autos, cuentas bancarias
    y consumos tiene registrados el fisco a nombre del contribuyente (clave para Ganancias y BBPP).
    """
    u, c = _get_credentials(usuario, clave)
    return _consultar_nuestra_parte(usuario=u, clave=c)

@mcp.tool()
def verificar_proveedor_apocrifo_apoc(cuit_proveedor: str) -> Dict[str, Any]:
    """
    Verifica en tiempo real si el CUIT de un proveedor figura en la Base e-APOC (Facturas Apócrifas /
    Contribuyentes No Confiables) de ARCA antes de computar Crédito Fiscal de IVA o deducir Ganancias.
    """
    return _verificar_apoc(cuit_proveedor=cuit_proveedor)

@mcp.tool()
def generar_pdf_factura_oficial(
    letra: str,
    emisor_razon_social: str,
    emisor_cuit: str,
    emisor_domicilio: str,
    emisor_condicion_iva: str,
    receptor_razon_social: str,
    receptor_cuit: str,
    receptor_condicion_iva: str,
    items: List[Dict[str, Any]],
    pto_vta: int = 1,
    nro_comprobante: int = 1,
    cae: str = "76471234567890",
    exportar_pdf_ruta: Optional[str] = None
) -> Dict[str, Any]:
    """
    Genera el comprobante oficial de ARCA (Factura A, B, C, E, FCE MiPyME o Nota de Crédito)
    en formato HTML imprimible y opcionalmente PDF A4, con código de comprobante y QR oficial RG 4892.
    """
    return _generar_pdf_factura(
        letra=letra,
        emisor_razon_social=emisor_razon_social,
        emisor_cuit=emisor_cuit,
        emisor_domicilio=emisor_domicilio,
        emisor_condicion_iva=emisor_condicion_iva,
        receptor_razon_social=receptor_razon_social,
        receptor_cuit=receptor_cuit,
        receptor_condicion_iva=receptor_condicion_iva,
        items=items,
        pto_vta=pto_vta,
        nro_comprobante=nro_comprobante,
        cae=cae,
        exportar_pdf_ruta=exportar_pdf_ruta
    )

@mcp.tool()
def configurar_estudio_contable(
    nombre_estudio: str,
    cuit_estudio: str,
    socio_responsable: str,
    branding_pie: Optional[str] = None
) -> Dict[str, Any]:
    """
    [MODO ESTUDIO CONTABLE B2B] Da de alta un estudio contable con su branding Marca Blanca
    para gestionar decenas o cientos de clientes desde Claude.
    """
    return _configurar_estudio(nombre_estudio, cuit_estudio, socio_responsable, branding_pie)

@mcp.tool()
def importar_cartera_clientes(
    estudio_id: str,
    clientes: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    [MODO ESTUDIO CONTABLE B2B] Alta masiva en lote de la cartera de clientes del estudio
    (CUIT, Razón Social, régimen, jurisdicciones, empleados y analista asignado).
    """
    return _importar_cartera(estudio_id, clientes)

@mcp.tool()
def tablero_cartera_estudio(
    estudio_id: str,
    periodo: Optional[str] = None,
    analista: Optional[str] = None
) -> Dict[str, Any]:
    """
    [MODO ESTUDIO CONTABLE B2B] Tablero consolidado de vencimientos por terminación de CUIT,
    semáforo de cierres (Rojo Anomalía / Amarillo Socio / Verde Aprobado) y carga por analista.
    """
    return _tablero_cartera(estudio_id, periodo, analista)

@mcp.tool()
def registrar_cierre_y_detectar_anomalias(
    estudio_id: str,
    cuit_cliente: str,
    periodo: str,
    impuesto: str,
    monto_actual: float,
    monto_mes_anterior: float = 0.0,
    preparado_por: str = "Analista Junior",
    notas: str = ""
) -> Dict[str, Any]:
    """
    [MODO ESTUDIO CONTABLE B2B] Carga un borrador de impuesto preparado por un analista,
    dispara alerta roja automática si hay desvío >30% respecto al mes anterior y lo deja en
    estado 'pendiente_revision_socio' (nunca presenta directo en ARCA).
    """
    return _registrar_cierre(estudio_id, cuit_cliente, periodo, impuesto, monto_actual, monto_mes_anterior, preparado_por, notas)

@mcp.tool()
def aprobar_cierres_socio(
    estudio_id: str,
    cierre_ids: List[str],
    aprobado_por: str,
    observaciones: str = ""
) -> Dict[str, Any]:
    """
    [MODO ESTUDIO CONTABLE B2B] El Socio revisa y aprueba en bloque los borradores validados
    habilitándolos para presentación en ARCA y envío Marca Blanca al cliente.
    """
    return _aprobar_cierres(estudio_id, cierre_ids, aprobado_por, observaciones)

@mcp.tool()
def generar_reporte_marca_blanca_cliente(
    nombre_estudio: str,
    razon_social_cliente: str,
    periodo: str,
    impuestos_a_pagar: List[Dict[str, Any]],
    ahorro_o_credito_rescatado: float = 0.0,
    recomendaciones_estudio: Optional[List[str]] = None,
    pie_firma_estudio: Optional[str] = None
) -> Dict[str, Any]:
    """
    [MODO ESTUDIO CONTABLE B2B] Genera el mensaje ejecutivo 100% Marca Blanca con el nombre
    y pie de firma del estudio contable, listo para enviar por WhatsApp o email al cliente final.
    """
    return _reporte_marca_blanca(
        nombre_estudio, razon_social_cliente, periodo, impuestos_a_pagar,
        ahorro_o_credito_rescatado, recomendaciones_estudio, pie_firma_estudio
    )

@mcp.tool()
def consultar_y_renovar_certificado_mipyme(
    cuit_empresa: Optional[str] = None,
    confirmado: bool = False,
    usuario: Optional[str] = None,
    clave: Optional[str] = None
) -> Dict[str, Any]:
    """
    Consulta la vigencia del Certificado MiPyME (F. 1272) en ARCA, verifica requisitos de
    renovación automática y prepara la solicitud/renovación para activar beneficios
    (100% Impuesto al Cheque a cuenta, IVA diferido 90 días, avales SGR). Requiere confirmado=True para enviar.
    """
    u, c = _get_credentials(usuario, clave)
    return _certificado_mipyme(usuario=u, clave=c, cuit_empresa=cuit_empresa, confirmado=confirmado)

@mcp.tool()
def obtener_protocolo_doublecheck_arca(consulta_o_dominio: str) -> Dict[str, Any]:
    """
    [OBLIGATORIO ANTES DE INFORMAR DEUDA O CUMPLIMIENTO] Devuelve la matriz de doble verificación
    (Double-Check) de ARCA para el dominio consultado (estado_de_cuenta_y_deudas, ganancias_personas_humanas,
    bienes_personales, iva_y_facturacion, empleador_seguridad_social) junto con los manuales oficiales relacionados.
    Impide falsos negativos como afirmar 'Deuda $0' mirando solo SCT sin revisar CCMA y Mis Facilidades.
    """
    from bot.doublecheck_arca import obtener_protocolo_doublecheck
    return obtener_protocolo_doublecheck(consulta_o_dominio)

@mcp.tool()
def validar_cobertura_auditoria_arca(
    dominio: str,
    fuentes_verificadas: List[str],
    fuentes_fallidas: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    [DOUBLE-CHECK OBLIGATORIO] Valida si se consultaron TODAS las fuentes obligatorias de ARCA
    antes de emitir un veredicto al contribuyente. Bloquea afirmaciones de 'Deuda $0' o 'Al día'
    cuando falta alguna fuente y emite el Sello de Verificación transparente.
    """
    from bot.doublecheck_arca import validar_cobertura_auditoria
    return validar_cobertura_auditoria(dominio, fuentes_verificadas, fuentes_fallidas)

@mcp.tool()
def obtener_playbook_servicio_tributario(servicio_o_consulta: str) -> Dict[str, Any]:
    """
    [PRE-FLIGHT OBLIGATORIO ANTES DE USAR CUALQUIER SERVICIO] Devuelve cómo se inicia un servicio
    de ARCA (SCT, CCMA, Mis Facilidades, Monotributo, Ganancias F.711/F.2711, BBPP F.762) u otro
    sistema tributario (AGIP CABA, ARBA PBA, SIFERE CM): qué dropdowns, fechas, botones de cálculo,
    paginación, popups o inputs ocultos requiere, qué NO muestra, y el Protocolo Pre-Flight Universal de 7 preguntas.
    """
    from bot.playbooks_servicios import obtener_playbook_servicio
    return obtener_playbook_servicio(servicio_o_consulta)

@mcp.tool()
def iniciar_sesion_contador_agentico(
    cuit: Optional[str] = None,
    situacion: str = "explorar"
) -> Dict[str, Any]:
    """
    [PUNTO DE ENTRADA RECOMENDADO AL INICIAR UNA CONVERSACIÓN] Presenta las capacidades reales
    del conector impuesto.com.ar, recupera el perfil fiscal guardado si existe, diagnostica qué
    conviene revisar HOY según la situación del usuario y guía un journey sin fricciones.
    """
    perfil = _obtener_perfil(cuit) if cuit else None
    return {
        "bienvenida": "Soy tu Contador Agéntico y CFO de impuesto.com.ar (47 herramientas conectadas a ARCA con Doble Verificación obligatoria y respaldo opcional de Contador Público Matriculado).",
        "perfil_guardado": perfil,
        "situacion": situacion,
        "capacidades": [
            "1. Auditoría de Deuda Real y Planes (CCMA + Mis Facilidades + SCT + Monotributo con Sello de Verificación)",
            "2. Facturación Electrónica con CAE y Cierre de IVA (Mis Comprobantes + Retenciones + Base e-APOC)",
            "3. Monotributo y Recategorización (margen vs. tope, exclusión, débito automático)",
            "4. Ganancias (F. 711 / F. 2711 Simplificada), SiRADIG y Bienes Personales (F. 762)",
            "5. PyMEs, Sueldos (F. 931) y Certificado MiPyME (F. 1272)",
            "6. Modo Estudio Contable B2B (cartera multi-cliente, alertas >30% y reportes Marca Blanca)"
        ],
        "siguiente_paso": "Contame tu situación (Monotributista, RI, PyME/Sociedad, Relación de Dependencia o Estudio Contable) o pasame tu CUIT para armarte el checklist exacto de hoy."
    }

if __name__ == "__main__":
    mcp.run()
