"""
bot/jurisprudencia_fiscal.py
Biblioteca de Jurisprudencia Tributaria Líder (CSJN, TFN, Comisión Arbitral)
y Matriz de Políticas Fiscales Provinciales y Municipales (TISH, SIRCREB, Sellos).

Permite a la IA y al usuario contar con respaldo doctrinario y jurisprudencial
para defenderse de abusos fiscales de ARCA, Rentas provinciales y Municipios,
explicado "como para un chico de 10 años" con sus citas técnicas oficiales.
"""

from typing import Dict, Any, List, Optional
import re

FALLOS_JURISPRUDENCIA = [
    {
        "id": "fallo_esso_tasas_municipales",
        "caratula": "Esso Petrolera Argentina S.R.L. c/ Municipalidad de Quilmes s/ acción declarativa de certeza",
        "tribunal": "Corte Suprema de Justicia de la Nación (CSJN)",
        "fecha": "23/03/2021",
        "tema": "Tasas Municipales de Inspección, Seguridad e Higiene (TISH) y base imponible",
        "analogia_10_anios": (
            "Imaginá que el encargado de la plaza te quiere cobrar una entrada altísima calculada sobre "
            "toda la plata que vos ganaste en el año, aunque vos solo fuiste una tarde a sentarte en un banco. "
            "La Corte Suprema dijo: 'El municipio no puede cobrarte como si fuera un socio de tus ganancias; "
            "la tasa municipal solo se cobra si te prestaron un servicio concreto (como pasar a inspeccionar tu local) "
            "y tiene que guardar una relación razonable con el costo de ese servicio'."
        ),
        "doctrina_legal": (
            "1) Toda tasa municipal requiere la existencia y acreditación de un servicio estatal efectivamente "
            "prestado de manera individualizada (doctrina de 'Laboratorios Raffo'). "
            "2) Es admisible tomar los ingresos brutos como base de cuantificación, pero siempre limitada "
            "a las actividades que tengan sustento territorial en el municipio y respetando el estándar de razonabilidad "
            "sin resultar confiscatoria ni desproporcionada con el costo del servicio."
        ),
        "como_lo_usa_el_cliente": (
            "Si un municipio del conurbano o del interior te reclama pagar la Tasa de Seguridad e Higiene "
            "solo porque despachaste un paquete por encomienda o tenés una antena de paso sin tener local ni depósito físico, "
            "este fallo es el escudo legal para rechazar la intimación."
        )
    },
    {
        "id": "fallo_laboratorios_raffo",
        "caratula": "Laboratorios Raffo S.A. c/ Municipalidad de Córdoba s/ demanda contencioso administrativa",
        "tribunal": "Corte Suprema de Justicia de la Nación (CSJN)",
        "fecha": "23/06/2009",
        "tema": "Inexistencia de local o establecimiento en el municipio (sustento territorial)",
        "analogia_10_anios": (
            "Si vos vendés tortas desde tu casa en Buenos Aires y alguien de Córdoba te compra una torta por internet, "
            "el intendente de Córdoba no puede mandarte una boleta de tasa de higiene porque vos no tenés ninguna cocina "
            "ni local en Córdoba para que ellos te limpien o inspeccionen."
        ),
        "doctrina_legal": (
            "Exige como presupuesto sine qua non para el cobro de la tasa de inspección comercial la existencia de un "
            "local, sucursal, oficina o establecimiento físico habilitado en el ejido municipal donde se preste efectivamente el servicio."
        ),
        "como_lo_usa_el_cliente": (
            "Defensa infalible para empresas de software, comercio electrónico y venta mayorista ante requerimientos de "
            "tasas municipales en localidades donde no tienen inmuebles ni oficinas."
        )
    },
    {
        "id": "fallo_candy_confiscatoriedad",
        "caratula": "Candy S.A. c/ AFIP y otro s/ amparo",
        "tribunal": "Corte Suprema de Justicia de la Nación (CSJN)",
        "fecha": "03/07/2009",
        "tema": "Ajuste por Inflación Impositivo en Impuesto a las Ganancias y Confiscatoriedad",
        "analogia_10_anios": (
            "Si con la inflación ganaste $100 pero todo subió tanto que esos $100 compran menos que antes, "
            "y el fisco no quiere calcular la inflación para cobrarte $60 de impuesto, te está comiendo tu capital. "
            "La Corte determinó que si el impuesto absorbe más de un tercio (33-35%) de lo que realmente ganaste, "
            "es inconstitucional porque te está confiscando tu patrimonio."
        ),
        "doctrina_legal": (
            "Fija el tope de confiscatoriedad en el 33% al 35% de la renta real devengada. Si la falta de aplicación "
            "del ajuste por inflación genera una alícuota efectiva superior a ese umbral, se viola el derecho de propiedad (Art. 17 C.N.)."
        ),
        "como_lo_usa_el_cliente": (
            "Permite a empresas aplicar el Ajuste por Inflación Impositivo integral en Ganancias y cuestionar liquidaciones ficticias de ARCA."
        )
    },
    {
        "id": "fallo_bayer_discriminacion_iibb",
        "caratula": "Bayer S.A. c/ Provincia de Santa Fe s/ acción declarativa de inconstitucionalidad",
        "tribunal": "Corte Suprema de Justicia de la Nación (CSJN)",
        "fecha": "31/10/2017",
        "tema": "Alícuotas discriminatorias de Ingresos Brutos a industrias de extraña jurisdicción",
        "analogia_10_anios": (
            "Es como si en un torneo cobraran la inscripción a $10 a los equipos de su barrio y a $50 a los que vienen "
            "de otro barrio para que no ganen. La Corte dijo que ninguna provincia puede cobrar impuestos más caros "
            "a las empresas solo porque sus fábricas están en otra provincia."
        ),
        "doctrina_legal": (
            "Las alícuotas agravadas de Ingresos Brutos a contribuyentes radicados fuera de la provincia violan la Cláusula Comercial "
            "(Art. 75 inc. 13 C.N.) y el principio de igualdad (Art. 16 C.N.), constituyendo aduanas interiores prohibidas."
        ),
        "como_lo_usa_el_cliente": (
            "Reclamo de repetición y devolución de saldos a favor cuando provincias como Buenos Aires (ARBA) o Santa Fe (API) "
            "aplican alícuotas más altas por no tener planta industrial en su territorio."
        )
    },
    {
        "id": "fallo_intercorp_embargos_afip",
        "caratula": "AFIP c/ Intercorp S.R.L. s/ ejecución fiscal",
        "tribunal": "Corte Suprema de Justicia de la Nación (CSJN)",
        "fecha": "15/06/2010",
        "tema": "Inconstitucionalidad de los embargos bancarios decretados por el fisco sin control judicial",
        "analogia_10_anios": (
            "Nadie puede ir y sacarte la plata de la alcancía por su cuenta sin pedirle primero permiso a un juez neutral. "
            "ARCA no puede congelar tus cuentas bancarias con un botón automático sin que un juez firme la orden."
        ),
        "doctrina_legal": (
            "Declara la inconstitucionalidad del Art. 92 de la Ley 11.683 que facultaba a los agentes fiscales a disponer "
            "embargos e inhibiciones generales de bienes sin previa orden de un juez competente."
        ),
        "como_lo_usa_el_cliente": (
            "Protección cautelar inmediata ante amenazas de trabas bancarias y embargos ejecutorios directos de ARCA o agencias provinciales."
        )
    },
    {
        "id": "res_comision_arbitral_rg5_2021",
        "caratula": "Resolución General 5/2021 de la Comisión Arbitral del Convenio Multilateral",
        "tribunal": "Comisión Arbitral del Convenio Multilateral",
        "fecha": "19/05/2021",
        "tema": "Comercio Electrónico, Marketplaces y Sustento Territorial Digital",
        "analogia_10_anios": (
            "Si tenés una tienda online o vendés por Mercado Libre, la ley dice que hay presencia comercial "
            "en la provincia donde vive la persona que te compró si utilizaste medios digitales para hacer llegar tu producto. "
            "Por eso tenés que repartir el impuesto con las reglas del Convenio para que no te retengan dos veces."
        ),
        "doctrina_legal": (
            "Reglamenta el sustento territorial en operaciones concertadas por medios electrónicos o telemáticos. "
            "Se considera configurado el sustento en la jurisdicción del domicilio del adquirente siempre que exista "
            "gasto atribuible o presencia digital sistemática."
        ),
        "como_lo_usa_el_cliente": (
            "Permite computar los coeficientes unificados en SIFERE CM03 y solicitar la reducción de alícuotas bancarias "
            "del padrón SIRCREB y SIRTAC (retenciones en plataformas de pago)."
        )
    }
]

POLITICAS_FISCALES_PROVINCIALES = {
    "CABA": {
        "organismo": "AGIP (Administración Gubernamental de Ingresos Públicos)",
        "normativa": "Código Fiscal de CABA y Ley Tarifaria Anual",
        "alicuotas_referencia": {
            "servicios": "3.0% a 5.0%",
            "comercio_minorista": "3.0%",
            "comercio_mayorista": "3.0% a 4.0%",
            "industria_manufacturera": "Exenta o 1.5% (según facturación)",
            "servicios_profesionales": "Exentos si están matriculados y organizados unipersonalmente (Art. 182 inc. 7 Código Fiscal)",
            "exportacion_servicios": "Exenta (Art. 182 Código Fiscal CABA)"
        },
        "regimenes_especiales": [
            "Distrito Tecnológico de Parque Patricios: Exención del 100% de Ingresos Brutos, Sellos y ABL para empresas TIC inscriptas.",
            "Régimen Simplificado de Ingresos Brutos para pequeños contribuyentes locales."
        ],
        "riesgos_retenciones": "Padrón de Retenciones y Percepciones AGIP con alícuotas de hasta el 4.5% si tenés inconsistencias registrales."
    },
    "PBA": {
        "organismo": "ARBA (Agencia de Recaudación de la Provincia de Buenos Aires)",
        "normativa": "Código Fiscal Ley 10.397 e Impositiva Anual",
        "alicuotas_referencia": {
            "servicios": "3.5% a 5.0%",
            "comercio": "3.5% a 5.0%",
            "industria": "1.5% o exenta si planta está radicada en PBA (cuestionable bajo fallo 'Bayer')",
            "profesionales": "3.5% (no gozan de exención general en PBA a diferencia de CABA)"
        },
        "regimenes_especiales": [
            "Monotributo Unificado PBA (ARBA + ARCA en una sola cuota mensual para evitar DDJJ de IIBB).",
            "Exención para microempresas y pymes industriales radicadas en parques industriales."
        ],
        "riesgos_retenciones": "ARBA RN 01/2011: Padrón de retención bancaria con alícuotas que pueden trepar al 5% si no se presentan DDJJ mensuales."
    },
    "CORDOBA": {
        "organismo": "Dirección General de Rentas de la Provincia de Córdoba",
        "normativa": "Código Tributario Provincial Ley 6.006",
        "alicuotas_referencia": {
            "servicios": "4.0% a 4.75%",
            "comercio": "4.0% a 4.75%",
            "industria": "0.5% a 1.5%",
            "software_y_tecnologia": "Exención provincial para empresas adheridas a la Ley de Economía del Conocimiento de Córdoba"
        },
        "regimenes_especiales": [
            "Monotributo Unificado Córdoba (MUC).",
            "Fondo para el Desarrollo Agropecuario e infraestructura vial."
        ],
        "riesgos_retenciones": "Retenciones bancarias agresivas para contribuyentes no inscriptos que tengan débitos en cuentas cordobesas."
    },
    "SANTA_FE": {
        "organismo": "API (Administración Provincial de Impuestos)",
        "normativa": "Código Fiscal Ley 3.456",
        "alicuotas_referencia": {
            "servicios": "4.5%",
            "comercio": "4.5%",
            "industria": "Exenta para establecimientos en Santa Fe (atención contingencia fallo 'Bayer' para extrañas jurisdicciones)."
        },
        "regimenes_especiales": [
            "Régimen Simplificado para pequeños contribuyentes santafesinos."
        ],
        "riesgos_retenciones": "SIRCREB Santa Fe con retención de hasta 5% sobre acreditaciones bancarias."
    },
    "MENDOZA": {
        "organismo": "ATM (Administración Tributaria Mendoza)",
        "normativa": "Código Fiscal Ley 9.432",
        "alicuotas_referencia": {
            "servicios": "4.0%",
            "comercio": "4.0%",
            "industria_vitivinicola": "Alícuotas diferenciadas y beneficios a bodegas y agroturismo."
        },
        "regimenes_especiales": [
            "Mendoza Activa (reintegros de inversión y crédito fiscal para pago de IIBB)."
        ],
        "riesgos_retenciones": "Retenciones interprovinciales por pagos recibidos de agentes de retención mendocinos."
    }
}

POLITICAS_MUNICIPALES_Y_TASAS = {
    "TISH_SEGURIDAD_E_HIGIENE": {
        "nombre": "Tasa de Inspección, Seguridad e Higiene (TISH) / Comercio e Industria",
        "descripcion": "Tributo municipal exigido por municipios de todo el país a actividades comerciales e industriales.",
        "requisito_constitucional": "Exige servicio efectivo e individualizado de inspección y sustento físico (local/sucursal/planta en el municipio) según fallos 'Laboratorios Raffo' y 'Esso'.",
        "abuso_frecuente": "Municipios que pretenden cobrar alícuotas sobre la facturación bruta total de una empresa que solo vendió por e-commerce o flete.",
        "defensa_recomendada": "Rechazo de oficio fundamentado en inexistencia de establecimiento en el ejido municipal y doctrina de la CSJN."
    },
    "TASA_VIAL_COMBUSTIBLES": {
        "nombre": "Tasa Vial Municipal sobre Carga de Combustible",
        "descripcion": "Recargo de entre 1.5% y 2.5% que cobran municipios sobre cada litro de nafta o gasoil.",
        "estado_juridico": "Ampliamente cuestionada por la Justicia Federal y la Secretaría de Comercio por constituir una doble imposición indebida sobre los impuestos a los combustibles líquidos."
    },
    "PUBLICIDAD_Y_PROPAGANDA": {
        "nombre": "Derecho de Publicidad y Propaganda",
        "descripcion": "Tasa por cartelería visible desde la vía pública.",
        "requisito": "Solo puede cobrarse si el cartel es visible desde la vía pública y está ubicado en el municipio cobrante. Prohibido cobrar por calcomanías interiores o marcas en vehículos de tránsito transitorio sin parada fija."
    }
}

def consultar_jurisprudencia(tema_o_conflicto: str) -> Dict[str, Any]:
    """
    Busca fallos líderes aplicables a una disputa o consulta fiscal.
    """
    q = (tema_o_conflicto or "").lower()
    resultados = []

    for f in FALLOS_JURISPRUDENCIA:
        texto_busqueda = (f["tema"] + " " + f["caratula"] + " " + f["doctrina_legal"]).lower()
        if any(w in texto_busqueda for w in q.split()) or q in texto_busqueda:
            resultados.append(f)

    if not resultados:
        # Fallback a los fallos principales
        resultados = FALLOS_JURISPRUDENCIA[:3]

    return {
        "consulta": tema_o_conflicto,
        "total_fallos_encontrados": len(resultados),
        "fallos_aplicables": resultados,
        "garantia_human_in_the_loop": "Podés pedir que un abogado o contador tributarista humano redacte tu descargo oficial basado en esta jurisprudencia."
    }

def consultar_politica_provincial_municipal(
    jurisdiccion: str,
    municipio: Optional[str] = None,
    rubro: Optional[str] = None
) -> Dict[str, Any]:
    """
    Informa sobre las alícuotas, exenciones y tasas municipales aplicables en una provincia o municipio.
    """
    j_norm = jurisdiccion.upper().strip()
    if "CABA" in j_norm or "BUENOS AIRES CIUDAD" in j_norm or "CAPITAL" in j_norm:
        clave = "CABA"
    elif "PBA" in j_norm or "PROVINCIA" in j_norm or "BUENOS AIRES" in j_norm:
        clave = "PBA"
    elif "CORDOBA" in j_norm or "CÓRDOBA" in j_norm:
        clave = "CORDOBA"
    elif "SANTA FE" in j_norm:
        clave = "SANTA_FE"
    elif "MENDOZA" in j_norm:
        clave = "MENDOZA"
    else:
        clave = "CABA"

    prov_info = POLITICAS_FISCALES_PROVINCIALES.get(clave, POLITICAS_FISCALES_PROVINCIALES["CABA"])

    # Info municipal si corresponde
    tasas_municipales = []
    if municipio or clave == "PBA":
        tasas_municipales.append(POLITICAS_MUNICIPALES_Y_TASAS["TISH_SEGURIDAD_E_HIGIENE"])
        tasas_municipales.append(POLITICAS_MUNICIPALES_Y_TASAS["TASA_VIAL_COMBUSTIBLES"])
        tasas_municipales.append(POLITICAS_MUNICIPALES_Y_TASAS["PUBLICIDAD_Y_PROPAGANDA"])

    return {
        "jurisdiccion": clave,
        "municipio_consultado": municipio or "Jurisdicción General",
        "politica_provincial": prov_info,
        "tasas_municipales_aplicables": tasas_municipales,
        "blindaje_constitucional": (
            "Para evitar cobros indebidos de tasas municipales, se aplican los fallos 'Esso' y 'Laboratorios Raffo': "
            "si no tenés local físico en ese municipio, no pueden cobrarte Tasa de Seguridad e Higiene."
        ),
        "explicacion_chico_10_anios": (
            f"En {clave}, la provincia te cobra una parte de lo que vendés (Ingresos Brutos). "
            "Pero si un intendente de un pueblo te quiere cobrar una tasa solo porque mandaste un paquete con una encomienda, "
            "el juez de la Corte Suprema le dice: '¡Pará la mano! Si no tenés una tienda abierta en su pueblo, no te pueden cobrar nada'."
        )
    }
