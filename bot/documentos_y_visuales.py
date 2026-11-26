"""
bot/documentos_y_visuales.py
Módulo de Conciliación de Documentación Off-ARCA (adjuntada por el usuario en el LLM)
y Generador de Reportes Visuales (Gráficos Mermaid, Semáforos y Diagramas Didácticos).

Resuelve el problema real de la contabilidad argentina: ARCA solo tiene una parte de la historia.
Para "armar la película completa", la IA solicita al cliente adjuntar extractos bancarios,
resúmenes de tarjetas, seguros, invoices del exterior y novedades de nómina, los concilia
y devuelve resultados con gráficos e ilustraciones de fácil comprensión.
"""

from typing import Dict, Any, List, Optional


CHECKLISTS_POR_TRAMITE = {
    "iva_mensual": {
        "titulo": "Cierre Mensual de IVA (F. 2002) y Libro IVA Digital",
        "lo_que_ya_tiene_arca": [
            "Facturas electrónicas emitidas (A, B, C, E) con CAE.",
            "Facturas electrónicas recibidas de proveedores argentinos."
        ],
        "pedir_al_cliente_adjuntar": [
            {
                "documento": "Extractos bancarios del mes (PDF o Excel)",
                "para_que_sirve": "Rescatar el IVA de comisiones bancarias, computar el Impuesto al Cheque (MiPyME) y auditar retenciones SIRCREB."
            },
            {
                "documento": "Resúmenes de tarjetas de crédito corporativas",
                "para_que_sirve": "Detectar IVA de servicios digitales del exterior (Meta Ads, Google, AWS, OpenAI) y gastos deducibles."
            },
            {
                "documento": "Tickets de peajes, combustible y gastos menores en papel",
                "para_que_sirve": "Sumar crédito fiscal y gastos operativos que a veces no impactan en Mis Comprobantes."
            },
            {
                "documento": "Despachos de importación o comprobantes de aduana (si aplica)",
                "para_que_sirve": "Computar el IVA de importación y percepciones aduaneras."
            }
        ],
        "mensaje_amigable_para_pedir": (
            "Ya bajé tus facturas desde ARCA, pero ARCA no ve toda la película. "
            "Para que no pagues ni un peso de más, arrastrá y soltá acá en el chat (en PDF, foto o Excel): "
            "1) Tus extractos bancarios del mes, 2) El resumen de tu tarjeta de crédito, y "
            "3) Cualquier ticket o comprobante de gasto que no sea factura electrónica."
        )
    },
    "ganancias_y_bbpp": {
        "titulo": "Declaración Anual de Ganancias y Bienes Personales",
        "lo_que_ya_tiene_arca": [
            "Facturación anual, retenciones sufridas y datos precargados en 'Nuestra Parte'."
        ],
        "pedir_al_cliente_adjuntar": [
            {
                "documento": "Extractos bancarios al 31 de diciembre (saldos finales)",
                "para_que_sirve": "Demostrar saldos en cajas de ahorro (100% exentos de BBPP) y justificar variación patrimonial."
            },
            {
                "documento": "Resúmenes de tarjetas de crédito del año",
                "para_que_sirve": "Recuperar percepciones de dólar tarjeta (30%) y deducir gastos vinculados a la actividad."
            },
            {
                "documento": "Pólizas de seguros (vida, retiro, auto afectado a la actividad) y medicina prepaga",
                "para_que_sirve": "Aplicar deducciones personales que bajan el Impuesto a las Ganancias."
            },
            {
                "documento": "Contratos de alquiler, escrituras de inmuebles o boletos de compraventa de autos",
                "para_que_sirve": "Valuar correctamente tus bienes y justificar el origen de fondos."
            },
            {
                "documento": "Invoices del exterior (software, hosting, viajes laborales)",
                "para_que_sirve": "Deducir gastos en dólares vinculados a tu negocio (Art. 83 LIG) aunque no tengan CAE argentino."
            }
        ],
        "mensaje_amigable_para_pedir": (
            "Para armar tu película anual completa y bajarte el impuesto todo lo que permite la ley, "
            "adjuntame acá en el chat (PDF o foto): tus resúmenes bancarios de diciembre, resúmenes de tarjeta, "
            "pólizas de seguros/prepaga, alquileres y cualquier gasto en dólares del exterior."
        )
    },
    "monotributo": {
        "titulo": "Control Integral de Monotributo y Recategorización",
        "lo_que_ya_tiene_arca": [
            "Facturas C / E emitidas en los últimos 12 meses y categoría vigente."
        ],
        "pedir_al_cliente_adjuntar": [
            {
                "documento": "Extractos bancarios y resúmenes de Mercado Pago / billeteras",
                "para_que_sirve": "Controlar que las acreditaciones bancarias no superen tu facturación ni el tope de categoría (principal causa de exclusión de oficio de ARCA)."
            },
            {
                "documento": "Resúmenes de tarjetas de crédito personales",
                "para_que_sirve": "Vigilar que tus consumos con tarjeta no disparen alertas de inconsistencia frente a tu categoría (Art. 20 inc. e Ley 24.977)."
            },
            {
                "documento": "Contrato de alquiler del local y boletas de luz (si tenés oficina/local)",
                "para_que_sirve": "Verificar parámetros físicos de recategorización (alquileres devengados y energía eléctrica)."
            }
        ],
        "mensaje_amigable_para_pedir": (
            "Ya revisé tu facturación en ARCA, pero ARCA también mira tus bancos y tarjetas para ver si te excluye. "
            "Adjuntame tus resúmenes de banco/Mercado Pago y tarjetas de los últimos meses así chequeo que estés 100% blindado."
        )
    },
    "sueldos_f931": {
        "titulo": "Liquidación Mensual de Sueldos y Formulario 931",
        "lo_que_ya_tiene_arca": [
            "Nómina declarada en Simplificación Registral y F. 931 del mes anterior."
        ],
        "pedir_al_cliente_adjuntar": [
            {
                "documento": "Planilla o mensaje con novedades del mes (horas extras, faltas, vacaciones, comisiones, bonos)",
                "para_que_sirve": "Calcular el recibo de sueldo exacto de cada empleado."
            },
            {
                "documento": "Certificados médicos o licencias (si hubo)",
                "para_que_sirve": "Liquidar correctamente días de enfermedad inculpable o licencia ART."
            },
            {
                "documento": "Factura de la póliza de ART y Seguro de Vida Colectivo",
                "para_que_sirve": "Verificar alícuota vigente de ART antes de cargar el Libro de Sueldos Digital."
            }
        ],
        "mensaje_amigable_para_pedir": (
            "Para liquidar los sueldos y el F. 931 de este mes, pasame o adjuntá en el chat las novedades de tu equipo "
            "(horas extras, comisiones, faltas, vacaciones o altas/bajas) y la última boleta de la ART."
        )
    }
}


def obtener_checklist_documentos_faltantes(
    tramite: str,
    tipo_personeria: str = "empresa"
) -> Dict[str, Any]:
    """
    Devuelve la lista exacta de documentos 'off-ARCA' que el usuario debe adjuntar en el LLM
    para armar la película contable completa antes de liquidar.
    """
    t_norm = (tramite or "").lower().strip()
    if "mono" in t_norm or "recat" in t_norm:
        clave = "monotributo"
    elif "sueldo" in t_norm or "931" in t_norm or "emplead" in t_norm:
        clave = "sueldos_f931"
    elif "ganancia" in t_norm or "bbpp" in t_norm or "bienes" in t_norm:
        clave = "ganancias_y_bbpp"
    else:
        clave = "iva_mensual"

    info = CHECKLISTS_POR_TRAMITE[clave]
    return {
        "tramite": clave,
        "tipo_personeria": tipo_personeria,
        **info,
        "explicacion_clara": (
            "ARCA solo registra tus facturas electrónicas, pero no ve tus movimientos bancarios, consumos en tarjeta, "
            "seguros ni comprobantes del exterior. Al adjuntar esos documentos en el chat, conciliamos la información "
            "completa para aprovechar todas las deducciones y evitar descalces."
        )
    }


def conciliar_y_generar_reporte_visual(
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
    Concilia los datos de ARCA con los comprobantes adjuntados por el cliente en el LLM
    (bancos, tarjetas, seguros, gastos no registrados) y genera:
    1. Ahorro fiscal real rescatado de los adjuntos.
    2. Alertas de descalce bancario vs facturación.
    3. Gráficos listos para renderizar (Mermaid pie chart, bar chart y barra visual).
    4. Explicación nivel chico de 10 años.
    """
    # Ahorro directo rescatado de los PDFs/fotos adjuntados en el LLM
    ahorro_gastos_off_arca = round(gastos_adjuntos_off_arca * 0.30, 2)  # ~30% impacto Ganancias/IVA
    ahorro_total_rescatado = round(
        ahorro_gastos_off_arca + impuesto_cheque_computable + percepciones_tarjeta_recuperables, 2
    )

    total_impuestos_brutos = round(iva_estimado + iibb_estimado + ganancias_o_cuota_estimada, 2)
    total_impuestos_netos = max(0.0, round(total_impuestos_brutos - ahorro_total_rescatado - retenciones_sircreb_banco, 2))
    gastos_totales = round(gastos_arca + gastos_adjuntos_off_arca, 2)
    ganancia_neta_bolsillo = max(0.0, round(facturacion_bruta - gastos_totales - total_impuestos_netos, 2))

    # Alerta de descalce bancario (acreditaciones vs facturación)
    alerta_bancaria = None
    if acreditaciones_bancarias_mes > 0 and facturacion_bruta > 0:
        diferencia = acreditaciones_bancarias_mes - facturacion_bruta
        ratio = acreditaciones_bancarias_mes / facturacion_bruta
        if ratio > 1.15:
            alerta_bancaria = {
                "nivel": "ALTO",
                "mensaje": (
                    f"Entraron ${acreditaciones_bancarias_mes:,.2f} a tus bancos pero facturaste ${facturacion_bruta:,.2f} "
                    f"(diferencia de ${diferencia:,.2f}). ARCA cruza los bancos todos los meses: "
                    "revisá si fueron transferencias entre cuentas propias, préstamos o ventas sin facturar."
                )
            }
        else:
            alerta_bancaria = {
                "nivel": "OK",
                "mensaje": "Tus acreditaciones bancarias guardan relación coherente con tu facturación declarada en ARCA."
            }

    # 1. Gráfico de Torta Mermaid (Distribución de tu facturación)
    mermaid_torta = (
        "```mermaid\n"
        "pie showData\n"
        '    title "A dónde va cada peso que facturaste este mes"\n'
        f'    "Tu ganancia limpia (bolsillo)" : {round(ganancia_neta_bolsillo, 2)}\n'
        f'    "Gastos operativos (ARCA + adjuntos)" : {round(gastos_totales, 2)}\n'
        f'    "Impuestos netos a pagar" : {round(total_impuestos_netos, 2)}\n'
        f'    "Plata ahorrada/recuperada de tus adjuntos" : {round(ahorro_total_rescatado, 2)}\n'
        "```"
    )

    # 2. Gráfico de Barras Mermaid (Comparativa Financiera)
    max_y = max(facturacion_bruta, gastos_totales, ganancia_neta_bolsillo, 1000) * 1.15
    mermaid_barras = (
        "```mermaid\n"
        "xychart-beta\n"
        '    title "Película Fiscal Completa del Mes (en ARS)"\n'
        '    x-axis ["Facturado", "Gastos", "Imp. Antes", "Imp. Final", "En Bolsillo"]\n'
        f'    y-axis "Pesos ($)" 0 --> {int(max_y)}\n'
        f'    bar [{int(facturacion_bruta)}, {int(gastos_totales)}, {int(total_impuestos_brutos)}, {int(total_impuestos_netos)}, {int(ganancia_neta_bolsillo)}]\n'
        "```"
    )

    # 3. Barra visual de tope (si aplica Monotributo)
    barra_tope = None
    if tope_categoria_anual and facturacion_acumulada_12m is not None and tope_categoria_anual > 0:
        pct = min(100.0, round((facturacion_acumulada_12m / tope_categoria_anual) * 100, 1))
        bloques_llenos = int(pct // 5)
        barra_ascii = "█" * bloques_llenos + "░" * (20 - bloques_llenos)
        semaforo = "🟢 SEGURO" if pct < 75 else ("🟡 ATENCIÓN" if pct < 90 else "🔴 RIESGO DE SALTO/EXCLUSIÓN")
        barra_tope = {
            "porcentaje_usado": pct,
            "margen_disponible": round(max(0.0, tope_categoria_anual - facturacion_acumulada_12m), 2),
            "barra_visual": f"[{barra_ascii}] {pct}% — {semaforo}"
        }

    # Resumen ejecutivo claro y directo (sin jerga ni infantilismos)
    analogia = (
        f"Sobre una facturación bruta de ${facturacion_bruta:,.0f}, tus gastos operativos totales "
        f"(ARCA + comprobantes adjuntos) fueron de ${gastos_totales:,.0f}. "
        f"Al conciliar tus resúmenes de banco, tarjeta y gastos complementarios rescatamos "
        f"${ahorro_total_rescatado:,.0f} de ahorro fiscal directo. "
        f"La carga tributaria neta queda en ${total_impuestos_netos:,.0f}, dejándote un resultado limpio "
        f"en bolsillo de ${ganancia_neta_bolsillo:,.0f}."
    )

    return {
        "resumen_numerico": {
            "facturacion_bruta": facturacion_bruta,
            "gastos_arca": gastos_arca,
            "gastos_adjuntos_off_arca": gastos_adjuntos_off_arca,
            "impuestos_sin_adjuntos": total_impuestos_brutos,
            "ahorro_rescatado_por_adjuntos": ahorro_total_rescatado,
            "retenciones_sircreb_computadas": retenciones_sircreb_banco,
            "impuestos_netos_finales": total_impuestos_netos,
            "ganancia_neta_bolsillo": ganancia_neta_bolsillo
        },
        "alerta_conciliacion_bancaria": alerta_bancaria,
        "termometro_tope": barra_tope,
        "graficos_para_mostrar_al_cliente": {
            "grafico_torta_mermaid": mermaid_torta,
            "grafico_barras_mermaid": mermaid_barras,
            "instruccion_renderizado_llm": (
                "MOSTRÁ OBLIGATORIAMENTE estos gráficos (en Mermaid, SVG o Artifact interactivo) al usuario "
                "junto con la explicación clara para que vea visualmente su situación fiscal de un vistazo."
            )
        },
        "explicacion_clara": analogia
    }


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
    Análisis económico-financiero integral contemplando la realidad operativa completa
    de una PyME en Argentina (circuito formal + informal) para medir rentabilidad real,
    cuantificar contingencias (juicios laborales, cruces bancarios ARCA Art. 18 Ley 11.683)
    y sugerir acciones estratégicas de ordenamiento, formalización rentable y protección de caja.
    """
    ventas_totales = ventas_formales_mes + ventas_informales_mes
    compras_totales = compras_formales_mes + compras_informales_mes
    pct_informalidad_ventas = round((ventas_informales_mes / ventas_totales) * 100, 1) if ventas_totales > 0 else 0.0
    margen_bruto_real = ventas_totales - compras_totales
    margen_bruto_formal = ventas_formales_mes - compras_formales_mes

    # Cuantificación de contingencia laboral por personal no registrado
    # Un juicio laboral por despido sin registro suele escalar entre 18 y 24 sueldos entre indemnización, costas e intereses
    contingencia_laboral_estimada = round(empleados_no_registrados * sueldo_promedio_bruto * 20, 2)
    costo_mensual_blanqueo_cargas = round(empleados_no_registrados * sueldo_promedio_bruto * 0.35, 2)

    riesgos = []
    sugerencias = []

    if cobra_informal_por_banco_o_mp and ventas_informales_mes > 0:
        riesgos.append({
            "tipo": "RIESGO_FISCAL_CRITICO_BANCARIO",
            "detalle": (
                "Cobrar ventas no facturadas a través de bancos, transferencias o Mercado Pago deja rastro directo. "
                "ARCA aplica presunción de ventas omitidas (Art. 18 inc. g Ley 11.683), reclamando IVA (21%) + Ganancias (35%) + multas del 50% al 100%."
            )
        })
        sugerencias.append(
            "Cortar de inmediato cobros digitales sin respaldo documental: todo ingreso bancario o por billetera virtual debe tener factura emitida o justificación contable."
        )

    if empleados_no_registrados > 0:
        riesgos.append({
            "tipo": "CONTINGENCIA_LABORAL_PATRIMONIAL",
            "detalle": (
                f"Tener {empleados_no_registrados} persona(s) sin registrar expone a la empresa a una contingencia estimada "
                f"de ${contingencia_laboral_estimada:,.0f} ante reclamos laborales o inspecciones del Ministerio de Trabajo / ARCA."
            )
        })
        sugerencias.append(
            "Evaluar regularización laboral bajo el régimen de la Ley Bases (Ley 27.742): permite blanquear relaciones laborales con condonación de multas y reducción de deuda de aportes, transformando un riesgo potencialmente destructivo en un costo previsible y deducible de Ganancias."
        )

    if compras_informales_mes > 0:
        riesgos.append({
            "tipo": "PERDIDA_CREDITO_FISCAL_Y_DISTORSION_MARGEN",
            "detalle": (
                f"Comprar ${compras_informales_mes:,.0f}/mes sin factura te impide descontar IVA Crédito Fiscal y te impide "
                "deducir ese costo en Ganancias, inflando artificialmente la ganancia imponible de tu balance formal."
            )
        })
        sugerencias.append(
            "Exigir factura en tus compras de mayor volumen: al formalizar compras, recuperás 21% de IVA y 30-35% de Ganancias, reduciendo drásticamente el costo neto de formalizar ventas."
        )

    sugerencias.append(
        "Activar Certificado MiPyME: permite computar 100% del Impuesto al Cheque como pago a cuenta de Ganancias, diferir el pago de IVA a 90 días y acceder a financiamiento bancario / SGR a tasas subsidiadas que compensan el costo impositivo."
    )

    return {
        "fotografia_economica_real": {
            "ventas_totales_reales_mes": ventas_totales,
            "porcentaje_ventas_fuera_circuito_formal": pct_informalidad_ventas,
            "margen_bruto_real_mes": margen_bruto_real,
            "margen_bruto_formal_visible_arca": margen_bruto_formal,
            "contingencia_laboral_estimada_total": contingencia_laboral_estimada,
            "costo_mensual_estimado_regularizar_nomina": costo_mensual_blanqueo_cargas
        },
        "riesgos_detectados": riesgos,
        "acciones_economico_financieras_sugeridas": sugerencias,
        "enfoque_asesor": (
            "Este análisis no juzga ni promueve evasión: mide tu rentabilidad real y cuantifica el riesgo oculto "
            "para armar una hoja de ruta de formalización gradual que proteja tu patrimonio y tu flujo de caja."
        )
    }
