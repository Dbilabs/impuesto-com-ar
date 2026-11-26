"""
bot/perfil_fiscal.py
Módulo de Onboarding y Determinación del Marco Fiscal del Contribuyente.
Permite a la IA comprender el contexto operativo del cliente:
- Rol y personería (Monotributo, Responsable Inscripto, SRL, SA, SAS)
- Actividad (qué vende)
- Mercado objetivo (a quién le vende: B2B, Consumidor final, Exterior)
- Ubicación y Jurisdicciones (CABA, PBA, Interior -> Local vs Convenio Multilateral SIFERE)
- Cantidad de empleados (Nómina, F. 931, ART, o sin empleados)

Genera:
1. Marco impositivo formal (ARCA, Rentas provinciales, BCRA, Ministerio de Trabajo).
2. Comprobantes fiscales autorizados (A, B, C, E, M).
3. Alertas de retenciones (SIRCREB, Ganancias RG 830, IVA RG 2854).
4. Explicación didáctica "como para un chico de 10 años".
"""

from typing import Dict, Any, List, Optional
import datetime

def evaluar_perfil_fiscal(
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
    Analiza las 5 variables de negocio del contribuyente y determina su marco impositivo exacto.
    """
    cuit_clean = "".join([c for c in str(cuit) if c.isdigit()])
    juris = [j.strip() for j in (jurisdicciones_operacion or [ubicacion_sede]) if j.strip()]
    if ubicacion_sede not in juris:
        juris.insert(0, ubicacion_sede)

    tipo_norm = tipo_personeria.lower().strip()
    es_monotributo = "mono" in tipo_norm
    es_persona_juridica = any(k in tipo_norm for k in ["srl", "s.r.l.", "sa", "s.a.", "sas", "sociedad", "empresa"])
    es_ri_persona_humana = ("inscripto" in tipo_norm or "autonomo" in tipo_norm or "ri" == tipo_norm) and not es_persona_juridica

    a_quien_norm = a_quien_vende.lower().strip()
    vende_exterior = any(k in a_quien_norm for k in ["exterior", "export", "afuera", "usa", "estados unidos", "eeuu", "extranjero", "europa", "latam", "dolar", "dólar"])
    vende_empresas = any(k in a_quien_norm for k in ["empresa", "b2b", "inscripto", "srl", "sa", "corporativo"])
    vende_consumidor = any(k in a_quien_norm for k in ["consumidor", "b2c", "gente", "publico", "local", "minorista", "final"])

    es_interjurisdiccional = len(juris) > 1 or "todas" in [j.lower() for j in juris] or "pais" in [j.lower() for j in juris]

    # 1. Régimen Nacional (ARCA)
    if es_monotributo:
        regimen_nacional = {
            "nombre": "Monotributo (Régimen Simplificado para Pequeños Contribuyentes - Ley 24.977)",
            "iva": "Exento / No alcanzado por IVA discriminado. Cuota única mensual integrada.",
            "ganancias": "Exento de Ganancias sobre los ingresos del régimen.",
            "jubilacion_salud": "Incluido en la cuota fija mensual del Monotributo (SIPAv y Obra Social).",
            "tope_anual_referencia": "$68.000.000 (según escalas vigentes Ley 27.743)"
        }
    elif es_persona_juridica:
        regimen_nacional = {
            "nombre": f"Persona Jurídica ({tipo_norm.upper()}) - Responsable Inscripto",
            "iva": "Obligación mensual: Presentación F. 2002 y Cierre de Libro de IVA Digital (RG 4597). Alícuota general 21%, 10.5% (bienes de capital) o 27% (telecomunicaciones/energía).",
            "ganancias": "Impuesto a las Ganancias Sociedades (30% a 35% de tasa corporativa escalonada) + 7% al distribuir dividendos (Ley de Impuesto a las Ganancias T.O. 2019).",
            "debito_credito": "Alcanzado por Impuesto al Cheque (Ley 25.413) 0.6% débito y 0.6% crédito (computable pago a cuenta según certificado MiPyME).",
            "regimenes_retencion": "Agente potencial de retención / Sujeto pasible de retenciones de IVA (RG 2854) y Ganancias (RG 830)."
        }
    else: # RI Persona Humana
        regimen_nacional = {
            "nombre": "Responsable Inscripto (Persona Humana / Autónomo)",
            "iva": "Obligación mensual: Presentación F. 2002 y Libro de IVA Digital (RG 4597). Débito fiscal menos Crédito fiscal.",
            "ganancias": "Ganancias Personas Humanas: Escala progresiva del 5% al 35% sobre ganancia neta anual. Deducción de gastos operativos (Art. 83 LIG).",
            "jubilacion_salud": "Aporte mensual obligatorio al Régimen General de Autónomos (Tablas categorías I a V).",
            "regimenes_retencion": "Pasible de retenciones comerciales de Ganancias (RG 830) e IVA."
        }

    # 2. Facturación y Comprobantes Habilitados
    comprobantes = []
    if es_monotributo:
        comprobantes.append({
            "tipo": "Factura C",
            "destinatarios": "Clientes en Argentina (Consumidores Finales, Empresas Responsables Inscriptas, otros Monotributistas)",
            "iva_discriminado": False,
            "regla": "No discrimina IVA. El monto cobrado es el total final."
        })
        if vende_exterior:
            comprobantes.append({
                "tipo": "Factura E (Exportación de Servicios)",
                "destinatarios": "Clientes en el exterior (empresas o personas no residentes)",
                "iva_discriminado": False,
                "regla": "Alícuota 0% IVA. Habilita el ingreso de hasta USD 24.000/año al dólar MEP/oficial sin liquidar obligatoriamente (Com. A 7518 BCRA)."
            })
    else: # Responsable Inscripto (Empresas o Personas)
        if vende_empresas:
            comprobantes.append({
                "tipo": "Factura A",
                "destinatarios": "Empresas y clientes que sean Responsables Inscriptos en IVA",
                "iva_discriminado": True,
                "regla": "Discrimina IVA (21%, 10.5% o 27%). Permite a tu cliente computar el Crédito Fiscal."
            })
        if vende_consumidor or es_monotributo:
            comprobantes.append({
                "tipo": "Factura B",
                "destinatarios": "Consumidores Finales, Monotributistas y Sujetos Exentos",
                "iva_discriminado": False,
                "regla": "El precio incluye el IVA pero no se discrimina en el cuerpo del comprobante."
            })
        if vende_exterior:
            comprobantes.append({
                "tipo": "Factura E (Exportación)",
                "destinatarios": "Clientes fuera de Argentina",
                "iva_discriminado": False,
                "regla": "Exento de IVA. Con derecho a recupero o devolución de créditos fiscales vinculados a la exportación."
            })

    # 3. Ingresos Brutos (Provincial)
    if es_interjurisdiccional:
        regimen_iibb = {
            "regimen": "Convenio Multilateral (SIFERE)",
            "alcance": f"Operás en {len(juris)} jurisdicciones ({', '.join(juris)}).",
            "declaracion": "Presentación mensual CM03 y anual CM05 con Coeficiente Unificado (Art. 2) o Régimen Especial.",
            "riesgo_sircreb": "CRÍTICO: Si vendés a varias provincias y no tenés dado de alta el Convenio Multilateral, el padrón SIRCREB ordenará a los bancos retenerte hasta un 5% de cada acreditación bancaria.",
            "recomendacion": "Mantener al día las DDJJ mensuales del CM03 para mantener alícuota SIRCREB en el tramo mínimo (0.01% - 1.5%)."
        }
    else:
        sede = juris[0] if juris else ubicacion_sede
        regimen_iibb = {
            "regimen": f"Régimen Local ({sede})",
            "alcance": f"Operaciones centralizadas únicamente en {sede}.",
            "declaracion": f"Declaración jurada mensual en Rentas de {sede} (ej. AGIP en CABA, ARBA en PBA, Rentas Córdoba).",
            "riesgo_sircreb": "BAJO: Alícuotas locales fijadas por el padrón de contribuyentes de la jurisdicción.",
            "recomendacion": "Si comenzás a despachar encomiendas o cobrar por Mercado Pago a clientes de otras provincias, se activará el sustento territorial para Convenio Multilateral."
        }

    # 4. Nómina y Empleados
    if cantidad_empleados > 0:
        regimen_laboral = {
            "tiene_empleados": True,
            "cantidad": cantidad_empleados,
            "obligaciones_mensuales": [
                "Formulario 931 ARCA (Cargas Sociales: Aportes del 17% + Contribuciones patronales del 18% a 20.4%)",
                "Libro de Sueldos Digital ARCA (RG 5249)",
                "Póliza de ART (Aseguradora de Riesgos del Trabajo)",
                "Seguro Colectivo de Vida Obligatorio (SCVO - Decreto 1567/74)",
                f"Aportes y Contribuciones Sindicales ({convenio_colectivo or 'Según CCT de la actividad'})"
            ],
            "costo_adicional_estimado": "Aproximadamente un +35% a +45% sobre el sueldo bruto básico acordado."
        }
    else:
        regimen_laboral = {
            "tiene_empleados": False,
            "cantidad": 0,
            "obligaciones_mensuales": [
                "Sin obligación de presentar Formulario 931 ni Libro de Sueldos Digital.",
                "Sin costos de ART patronal ni seguros obligatorios de nómina."
            ],
            "costo_adicional_estimado": "$0 (Cero costo previsional patronal)."
        }

    # 5. Recomendaciones Estratégicas Clave
    recomendaciones = []
    if vende_exterior:
        recomendaciones.append({
            "titulo": "Aprovechar Cupo BCRA de USD 24.000",
            "detalle": "Tus cobros del exterior con Factura E tienen dispensa de liquidación forzosa en pesos hasta USD 24.000 por año calendario (Com. A 7518 BCRA). Conservás los dólares billete en tu cuenta bancaria local."
        })
    if es_monotributo and vende_empresas:
        recomendaciones.append({
            "titulo": "Vigilancia de Escala para no perder clientes B2B",
            "detalle": "Al ser Monotributista emitís Factura C. Si tus clientes son grandes empresas RI, algunos prefieren Factura A para descontar IVA. Si estás cerca de la Categoría K, proyectá la creación de una S.R.L. para no frenar tu crecimiento."
        })
    if es_persona_juridica:
        recomendaciones.append({
            "titulo": "Certificado MiPyME Activo",
            "detalle": "Tramitar y renovar el Certificado MiPyME ante la Secretaría Pyme: reduce la tasa de Ganancias, permite computar 100% del Impuesto al Cheque como pago a cuenta y aplaza el pago del IVA a 90 días."
        })
    if es_interjurisdiccional:
        recomendaciones.append({
            "titulo": "Blindaje contra SIRCREB Abusivo",
            "detalle": "La IA auditará mensualmente tus extractos bancarios. Si un banco te retiene más de lo que marca tu coeficiente de Convenio, se genera el reclamo automático ante la Comisión Arbitral."
        })

    # 6. Explicación como a un chico de 10 años
    analogia = _generar_analogia_10_anios(
        tipo_personeria=tipo_personeria,
        que_vende=que_vende,
        a_quien_vende=a_quien_vende,
        ubicacion=ubicacion_sede,
        tiene_empleados=(cantidad_empleados > 0)
    )

    return {
        "perfil_recibido": {
            "cuit": cuit_clean,
            "razon_social": razon_social or "Contribuyente Registrado",
            "rol": rol or "Titular del negocio",
            "tipo_personeria": tipo_norm,
            "actividad": que_vende,
            "clientes": a_quien_vende,
            "sede": ubicacion_sede,
            "jurisdicciones": juris,
            "empleados": cantidad_empleados,
            "convenio_colectivo": convenio_colectivo or "No especificado"
        },
        "diagnostico_fiscal": {
            "regimen_nacional": regimen_nacional,
            "comprobantes_habilitados": comprobantes,
            "ingresos_brutos": regimen_iibb,
            "cargas_sociales": regimen_laboral,
            "recomendaciones_estrategicas": recomendaciones
        },
        "explicacion_chico_10_anios": analogia,
        "proximos_pasos_ia": [
            "1. La IA ya conoce tu mapa: cada vez que le pidas facturar, elegirá la letra correcta (A, B, C o E) sin que tengas que dudar.",
            "2. Tus recordatorios ahora se filtran por tu realidad: no te molestará con vencimientos de sueldos si no tenés empleados.",
            "3. Cuando ingreses dinero al banco, la IA vigilará que no te cobren retenciones indebidas de Ingresos Brutos."
        ]
    }

def _generar_analogia_10_anios(
    tipo_personeria: str,
    que_vende: str,
    a_quien_vende: str,
    ubicacion: str,
    tiene_empleados: bool
) -> str:
    """
    Produce una analogía didáctica y empática adaptada al caso puntual.
    """
    p = tipo_personeria.lower()
    if "mono" in p:
        intro = (
            f"Con tu actividad ({que_vende}) radicada en {ubicacion}, el Monotributo te simplifica todo en una cuota fija mensual "
            "que ya incluye impuesto, jubilación y obra social, siempre que no superes el tope anual de facturación. "
            "Emitís Factura C en el país (sin discriminar IVA) y tu prioridad es monitorear el margen disponible para no quedar excluido."
        )
    elif "srl" in p or "sa" in p:
        intro = (
            f"Al operar como sociedad ({que_vende} en {ubicacion}), la empresa tiene patrimonio separado del tuyo personal. "
            "Liquidás IVA mensualmente (cobrando 21% en Factura A y descontando el IVA de tus compras operativas) y tributás Ganancias "
            "sobre el resultado neto anual. Tu foco estratégico es deducir bien todos los gastos del negocio y planificar tus retiros (honorarios vs dividendos)."
        )
    else:
        intro = (
            f"Como Responsable Inscripto ({que_vende} en {ubicacion}), actuás en el régimen general: cobrás IVA en tus ventas y "
            "descontás el IVA de todas tus compras vinculadas a la actividad, ingresando solo la diferencia. En Ganancias tributás "
            "por escala progresiva, por lo que documentar cada gasto operativo es clave para cuidar tu rentabilidad."
        )

    if tiene_empleados:
        empleados_txt = (
            " Al tener personal en relación de dependencia, cada mes se liquidan sueldos, cargas sociales (F. 931), "
            "Libro de Sueldos Digital y ART — con un costo total aproximado de +35% a +45% sobre el bruto."
        )
    else:
        empleados_txt = (
            " Al no tener nómina en blanco, evitás por completo la carga mensual de F. 931 y ART."
        )

    return intro + empleados_txt
