"""Secciones: Ingresos Brutos, Ganancias y Retenciones."""
from lib import cta, table, quiz, PROVINCIAS, esc, ARCA, COMARB
import config as C

PAGES = []
GAN_ARCA = ("ARCA — Ganancias personas jurídicas: escala", "https://www.afip.gob.ar/gananciasYBienes/ganancias/personas-juridicas/determinacion/escala.asp")
MIS_RET = ("ARCA — Mis Retenciones", "https://www.arca.gob.ar/")
prov_opts = "".join(f"<option>{esc(p)}</option>" for p in PROVINCIAS)

# ------------------------------------------------------------------ INGRESOS BRUTOS
CM_TOOL = f"""<div class="tool" id="calc-cm">
<h2 style="margin:0 0 4px;font-size:23px">Simulador de coeficientes del Convenio Multilateral</h2>
<p style="margin:0;color:var(--muted)">Cargá ingresos y gastos del ejercicio anterior por provincia (régimen general: 50% ingresos, 50% gastos).</p>
<template id="cm-row"><div class="row2 cm-row" style="grid-template-columns:2fr 1fr 1fr auto;align-items:end">
<div><label>Provincia</label><select class="cm-prov">{prov_opts}</select></div>
<div><label>Ingresos</label><input class="cm-ing" type="text" inputmode="numeric" placeholder="0"></div>
<div><label>Gastos</label><input class="cm-gas" type="text" inputmode="numeric" placeholder="0"></div>
<button type="button" class="btn sec sm cm-del" aria-label="Quitar provincia" style="margin-bottom:2px">✕</button></div></template>
<div id="cm-rows"></div>
<button type="button" class="btn sec sm" id="cm-add" style="margin-top:12px">+ Agregar provincia</button>
<label for="cm-base">Base imponible del mes (opcional, para repartirla)</label><input id="cm-base" type="text" inputmode="numeric" placeholder="Ej.: 50.000.000">
<div class="result" id="cm-out" hidden aria-live="polite"></div>
</div>"""

PAGES.append(dict(
    path="/iibb/", kind="article", crumbs=[("Ingresos Brutos", "/iibb/")],
    title="Ingresos Brutos para empresas: guía y simulador",
    description="Cómo funciona Ingresos Brutos para empresas: alícuotas por provincia, Convenio Multilateral, regímenes de retención y percepción, padrones y saldos a favor.",
    h1="Ingresos Brutos para empresas: cómo pagar lo justo en cada provincia",
    about=["Ingresos Brutos", "Convenio Multilateral", "Regímenes de recaudación"],
    answer=("<p><strong>Ingresos Brutos</strong> es un impuesto provincial sobre la facturación: cada provincia fija sus alícuotas según la actividad. Si vendés en varias provincias, "
            "el <strong>Convenio Multilateral</strong> reparte la base entre ellas con un coeficiente (50% ingresos, 50% gastos en el régimen general). Además, las provincias "
            "cobran por adelantado con <strong>retenciones, percepciones y el sistema bancario SIRCREB</strong>, que suelen generar saldos a favor si nadie los controla.</p>"),
    body=CM_TOOL + f"""
<h2>Las 4 cosas que más impactan en lo que pagás</h2>
{table(["Tema", "Qué revisar"], [
        ["Alícuota de tu actividad", "Que el código de actividad declarado sea el correcto: un código mal elegido puede tener otra alícuota."],
        ["Coeficientes del Convenio", "Que se recalculen al inicio de cada ejercicio, con ingresos y gastos bien asignados."],
        ["Alícuotas de padrón", "Las provincias asignan alícuotas de retención y percepción según su evaluación de riesgo; pueden ser más altas de lo que corresponde."],
        ["Saldos a favor", "Si las retenciones superan el impuesto todos los meses, se puede pedir exclusión o reducción."],
    ])}
<h2>Local o Convenio Multilateral</h2>
<p>Si toda tu actividad está en una provincia, tributás como <strong>contribuyente local</strong> ante su agencia de recaudación. Si hay ingresos y gastos en más de una, corresponde el <strong>Convenio Multilateral</strong>: se presenta en el sistema SIFERE con declaraciones mensuales y una anual. Más detalle en la <a href="/empresas/convenio-multilateral/">guía del Convenio Multilateral</a>.</p>
<h2>Retenciones, percepciones y SIRCREB</h2>
<p>Las provincias designan agentes (bancos, grandes empresas) que retienen o perciben Ingresos Brutos como pago a cuenta. Bien computados reducen el saldo a pagar; mal controlados, se acumulan como saldo a favor. Mirá la <a href="/retenciones/">guía de retenciones</a> y el <a href="/empresas/saldos-a-favor/">estimador de saldos a favor</a>.</p>
{cta("empresa", "convenio-multilateral", "¿Pagás Ingresos Brutos en varias provincias?", "Un especialista revisa tus coeficientes, alícuotas y saldos por jurisdicción.", button="Revisar mi Ingresos Brutos")}""",
    faqs=[
        ("¿La alícuota de Ingresos Brutos es igual en todas las provincias?", "No. Cada provincia fija sus alícuotas en su ley impositiva anual, según la actividad y a veces según la facturación."),
        ("¿Cómo se calcula el coeficiente del Convenio Multilateral?", "En el régimen general, la mitad surge de la proporción de ingresos de cada provincia y la otra mitad de la proporción de gastos, tomando el balance del ejercicio anterior."),
        ("¿Qué es el SIRCREB?", "Es el sistema de recaudación de Ingresos Brutos sobre las acreditaciones bancarias: el banco retiene un porcentaje de lo que entra en tu cuenta como pago a cuenta del impuesto."),
    ],
    sources=[COMARB, ARCA],
    related=["/empresas/convenio-multilateral/", "/retenciones/", "/empresas/saldos-a-favor/"],
    side_cta=("empresa", "convenio-multilateral", "Revisá tu Ingresos Brutos", "Coeficientes, alícuotas de padrón y saldos a favor. Primera consulta sin costo."),
    schema=[{"@type": "WebApplication", "name": "Simulador de coeficientes del Convenio Multilateral", "applicationCategory": "FinanceApplication", "operatingSystem": "Web",
             "offers": {"@type": "Offer", "price": "0", "priceCurrency": "ARS"}, "url": C.SITE_URL + "/iibb/"}],
))

# ------------------------------------------------------------------ GANANCIAS
ANT_TOOL = """<form class="tool" id="calc-anticipos" novalidate>
<h2 style="margin:0 0 4px;font-size:23px">¿Estás pagando anticipos de más?</h2>
<p style="margin:0;color:var(--muted)">Los anticipos se calculan sobre el impuesto del año anterior. Si este año la empresa gana menos, estás financiando al fisco.</p>
<div class="row2">
<div><label for="an-base">Impuesto determinado del ejercicio anterior</label><input id="an-base" type="text" inputmode="numeric" placeholder="Ej.: 120.000.000"></div>
<div><label for="an-est">Impuesto estimado para este ejercicio</label><input id="an-est" type="text" inputmode="numeric" placeholder="Ej.: 60.000.000"></div>
</div>
<label for="an-pag">Anticipos ya pagados este ejercicio (opcional)</label><input id="an-pag" type="text" inputmode="numeric" placeholder="0">
<button class="btn" type="submit" style="margin-top:16px">Calcular</button>
<div class="result" hidden aria-live="polite"></div>
</form>"""

PAGES.append(dict(
    path="/ganancias/", kind="article", crumbs=[("Ganancias", "/ganancias/")],
    title="Impuesto a las Ganancias para empresas: escala y anticipos",
    description="Ganancias para sociedades y responsables inscriptos: escala 2026 del 25% al 35%, anticipos, reducción de anticipos y planificación para pagar lo justo.",
    h1="Impuesto a las Ganancias: escala, anticipos y cómo planificarlo",
    about=["Impuesto a las Ganancias", "Anticipos", "Sociedades"],
    answer=("<p>Las <strong>sociedades</strong> (SA, SRL, SAS) pagan Ganancias con una escala de <strong>25%, 30% y 35%</strong> según la ganancia neta; para ejercicios iniciados en 2026, "
            "el 25% rige hasta unos $133 millones y el 35% por encima de unos $1.332 millones. Durante el año se pagan <strong>anticipos</strong> calculados sobre el impuesto del ejercicio anterior: "
            "si este año la empresa gana menos, se puede <strong>pedir la reducción</strong> y liberar caja. Las personas humanas tributan con otra escala, del 5% al 35%.</p>"),
    body=ANT_TOOL + f"""
<h2>Escala para sociedades (ejercicios iniciados en 2026)</h2>
{table(["Ganancia neta imponible", "Alícuota"], [["Primer tramo (hasta unos $133 millones)", "25%"], ["Segundo tramo (hasta unos $1.332 millones)", "30% sobre el excedente, más un monto fijo"], ["Más de unos $1.332 millones", "35% sobre el excedente, más un monto fijo"]],
            caption="Los tramos se actualizan cada año por inflación. Verificá los montos exactos en la tabla de ARCA según el inicio de tu ejercicio. Los dividendos tienen una retención adicional del 7%.")}
<h2>Dónde suele estar la plata en Ganancias</h2>
<ul>
<li><strong>Anticipos sobre un año mejor:</strong> la reducción libera caja durante el ejercicio.</li>
<li><strong>Gastos deducibles no computados</strong> por falta de comprobante o mala registración.</li>
<li><strong>Ajuste por inflación impositivo</strong> mal calculado.</li>
<li><strong>Quebrantos de años anteriores</strong> que no se están usando.</li>
<li><strong>Retenciones sufridas</strong> que no se computan contra el impuesto (ver <a href="/retenciones/">retenciones</a>).</li>
</ul>
<h2>Reducción de anticipos: cómo funciona</h2>
<p>Se solicita en ARCA con fundamento en una estimación del impuesto del año, cuando la suma de anticipos supera esa estimación en los porcentajes que fija la normativa. Si al final el impuesto resulta mayor que lo estimado, se pagan intereses sobre la diferencia; por eso conviene hacerlo con una proyección seria.</p>
{cta("empresa", "planificacion", "Planificá Ganancias antes del cierre", "Un especialista revisa anticipos, deducciones y quebrantos y te dice cuánto podés liberar.", button="Quiero planificar Ganancias")}""",
    faqs=[
        ("¿Qué alícuota de Ganancias paga una SAS?", "La misma escala que el resto de las sociedades: 25%, 30% o 35% según la ganancia neta imponible, con tramos que se actualizan cada año."),
        ("¿Se puede reducir los anticipos de Ganancias?", "Sí. Si estimás que el impuesto del ejercicio va a ser menor que la base de los anticipos, podés pedir la reducción en ARCA. Si el impuesto final resulta mayor, se deben intereses."),
        ("¿Cuándo vence la declaración de Ganancias de una sociedad?", "En el quinto mes posterior al cierre del ejercicio, según la terminación del CUIT."),
    ],
    sources=[GAN_ARCA, ARCA],
    related=["/retenciones/", "/empresas/fiscalizacion-arca/", "/iva/"],
    side_cta=("empresa", "planificacion", "¿Pagás anticipos de más?", "Revisamos tu proyección de Ganancias sin costo."),
    schema=[{"@type": "WebApplication", "name": "Calculadora de exceso de anticipos de Ganancias", "applicationCategory": "FinanceApplication", "operatingSystem": "Web",
             "offers": {"@type": "Offer", "price": "0", "priceCurrency": "ARS"}, "url": C.SITE_URL + "/ganancias/"}],
))

# ------------------------------------------------------------------ RETENCIONES
PAGES.append(dict(
    path="/retenciones/", kind="article", crumbs=[("Retenciones y percepciones", "/retenciones/")],
    title="Retenciones y percepciones: cómo dejar de financiar al fisco",
    description="Qué son las retenciones y percepciones de IVA, Ganancias e Ingresos Brutos, cómo controlarlas en Mis Retenciones y cómo pedir exclusión o reducción.",
    h1="Retenciones y percepciones: cómo controlarlas y dejar de financiar al fisco",
    about=["Retenciones", "Percepciones", "Certificado de exclusión", "Saldos a favor"],
    answer=("<p>Una <strong>retención</strong> te la descuenta quien te paga; una <strong>percepción</strong> te la cobra de más quien te vende. Ambas son pagos a cuenta de IVA, Ganancias o "
            "Ingresos Brutos. Si no las computás, pagás dos veces; si superan el impuesto, se acumulan como <strong>saldo a favor</strong>. Se controlan en <strong>Mis Retenciones</strong> "
            "(ARCA) y en los sistemas de cada provincia, y en muchos casos se puede pedir un <strong>certificado de exclusión o reducción</strong>.</p>"),
    body=quiz("test-retenciones", "¿Te están reteniendo de más?", [
        ("¿Todos los meses te queda saldo a favor de Ingresos Brutos o de IVA?", 1),
        ("¿Tu margen es bajo comparado con lo que facturás?", 1),
        ("¿Vendés a grandes empresas o al Estado (agentes de retención)?", 1),
        ("¿Te retienen Ingresos Brutos en el banco (SIRCREB) en provincias donde casi no operás?", 1),
        ("¿Nadie concilia lo que te retienen con lo que informan los agentes?", 1),
        ("¿Nunca pediste un certificado de exclusión o reducción?", 1),
    ], [
        {"min": 0, "title": "Todo en orden", "text": "No aparecen señales de retenciones excesivas. Igual conviene conciliarlas una vez por mes."},
        {"min": 2, "title": "Hay señales de retenciones de más", "text": "Es probable que estés financiando al fisco. Hay herramientas para frenarlo: exclusión, reducción o revisión de alícuotas de padrón."},
        {"min": 4, "title": "Estás financiando al fisco", "text": "Con este perfil se suelen acumular saldos importantes. Un plan de exclusión y recupero puede liberar capital de trabajo."},
    ], "/diagnostico/?perfil=empresa&tema=saldos-a-favor", "Quiero frenar las retenciones") + f"""
<h2>Retenciones y percepciones por impuesto</h2>
{table(["Impuesto", "Quién retiene o percibe", "Cómo se recupera"], [
        ["IVA", "Grandes contribuyentes, tarjetas, el Estado, aduana", "Se computa en la declaración mensual; el excedente es saldo de libre disponibilidad"],
        ["Ganancias", "Clientes agentes de retención, bancos y otros regímenes", "Se computa en la declaración anual; el excedente es saldo a favor"],
        ["Ingresos Brutos", "Agentes provinciales, bancos (SIRCREB), aduana", "Se computa en la declaración mensual de cada provincia o del Convenio"],
    ])}
<h2>Cómo controlarlas</h2>
<ol>
<li>Descargá todos los meses <strong>Mis Retenciones</strong> en ARCA y el detalle de cada provincia.</li>
<li>Conciliá contra tus cobranzas y extractos bancarios: cada retención tiene que tener su certificado.</li>
<li>Computalas en la declaración del período que corresponde; si te las olvidás, se pierde plata.</li>
<li>Si generan saldo a favor de forma sistemática, evaluá pedir <strong>exclusión o reducción</strong>: en IVA, ante ARCA; en Ingresos Brutos, ante cada provincia.</li>
</ol>
{cta("empresa", "saldos-a-favor", "Dejá de financiar al fisco", "Un especialista revisa tus retenciones por impuesto y provincia y arma el plan de exclusión y recupero.", button="Revisar mis retenciones")}""",
    faqs=[
        ("¿Dónde veo las retenciones que me hicieron?", "En el servicio Mis Retenciones de ARCA para los impuestos nacionales, y en los sistemas de cada agencia provincial (o SIRCREB) para Ingresos Brutos."),
        ("¿Se puede pedir que no me retengan IVA?", "Sí, cuando las retenciones y percepciones generan saldos a favor de manera sistemática, se puede tramitar un certificado de exclusión ante ARCA, sujeto a requisitos."),
        ("¿Qué pasa si no computo una retención?", "Terminás pagando el impuesto dos veces. Se puede rectificar la declaración, pero conviene conciliar todos los meses."),
    ],
    sources=[MIS_RET, COMARB],
    related=["/empresas/saldos-a-favor/", "/iibb/", "/iva/"],
    side_cta=("empresa", "saldos-a-favor", "¿Te retienen de más?", "Plan de exclusión y recupero con un especialista. Primera consulta sin costo."),
))
