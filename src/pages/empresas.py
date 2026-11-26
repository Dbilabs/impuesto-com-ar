"""Páginas para empresas medianas: impuestos y auditoría."""
from lib import cta, quiz, table, ARCA, COMARB, IGJ, LGS, BO
import config as C

EMP = ("Empresas", "/empresas/")
PAGES = []

# ------------------------------------------------------------------ hub
PAGES.append(dict(
    path="/empresas/", kind="article", crumbs=[EMP],
    title="Impuestos que te hacen más competitivo: guía para empresas",
    description="Impuestos bien llevados son plata que vuelve a tu empresa: saldos a favor, planificación fiscal, auditoría, fiscalizaciones de ARCA y Convenio Multilateral.",
    h1="Impuestos bien llevados: plata que vuelve a tu empresa",
    about=["Impuestos para empresas", "Auditoría de estados contables"],
    answer=("<p>Los impuestos no son solo un costo: bien gestionados liberan capital de trabajo y te hacen <strong>más competitivo</strong>. Las empresas medianas suelen perder plata en tres lugares: <strong>saldos a favor</strong> de IVA e Ingresos Brutos que se acumulan sin gestionarse, "
            "<strong>contingencias</strong> que aparecen recién en una fiscalización, y <strong>planificación fiscal</strong> que nadie revisa. Además, muchas necesitan "
            "<strong>estados contables auditados</strong> para la IGJ, un banco, una licitación o su casa matriz. Acá tenés guías y diagnósticos para cada caso.</p>"),
    body=f"""
<div class="grid" style="margin-top:8px">
<a class="card" href="/empresas/saldos-a-favor/"><h3>¿Cuánta plata tenés atrapada en saldos a favor?</h3><p>Estimá en un minuto el saldo de IIBB e IVA que se acumula y cómo recuperarlo.</p><span class="go">Estimar mi saldo →</span></a>
<a class="card" href="/empresas/auditoria-de-estados-contables/"><h3>¿Tu empresa necesita auditar sus estados contables?</h3><p>Test rápido: IGJ, bancos, SGR, licitaciones y casa matriz.</p><span class="go">Hacer el test →</span></a>
<a class="card" href="/empresas/fiscalizacion-arca/"><h3>¿Resistirías una fiscalización de ARCA?</h3><p>Checklist de 8 puntos para detectar contingencias antes que el fisco.</p><span class="go">Revisar mi riesgo →</span></a>
<a class="card" href="/empresas/convenio-multilateral/"><h3>Convenio Multilateral</h3><p>Cómo se reparte Ingresos Brutos cuando vendés en varias provincias.</p><span class="go">Leer la guía →</span></a>
<a class="card" href="/empresas/precios-de-transferencia/"><h3>Precios de transferencia</h3><p>Umbrales vigentes y obligaciones con vinculadas del exterior.</p><span class="go">Leer la guía →</span></a>
<a class="card" href="/empresas/como-elegir-estudio-contable/"><h3>Cómo elegir estudio contable</h3><p>Criterios y plantilla de pedido de propuesta para comparar estudios.</p><span class="go">Descargar plantilla →</span></a>
</div>
<h2>¿Qué no te está diciendo tu departamento de impuestos?</h2>
<p>No suele ser mala fe: el equipo está ocupado cumpliendo vencimientos y no tiene tiempo de mirar oportunidades. Una segunda opinión independiente revisa lo que el día a día no deja ver:</p>
<ul>
<li>Saldos a favor que crecen todos los meses y nadie gestiona.</li>
<li>Alícuotas de retención o percepción más altas de lo que corresponde.</li>
<li>Coeficientes de Convenio Multilateral desactualizados.</li>
<li>Beneficios, regímenes o reducciones de anticipos que no se están usando.</li>
<li>Contingencias que un cruce sistémico de ARCA puede detectar antes que vos.</li>
</ul>
{cta("empresa", "planificacion", "Pedí una segunda opinión sobre tus impuestos", "Un especialista revisa tu situación y te muestra dónde podés ganar competitividad. Primera reunión sin costo.", button="Quiero una segunda opinión")}""",
    faqs=[
        ("¿Qué es una empresa mediana para este sitio?", "Hablamos de empresas con equipos administrativos propios, que suelen facturar varios cientos o miles de millones de pesos por año, operar en más de una provincia o tener obligaciones de auditoría."),
        ("¿Con qué estudios trabajan?", "Trabajamos con estudios contables aliados especializados en impuestos corporativos, auditoría y planificación fiscal."),
    ],
    related=["/empresas/saldos-a-favor/", "/empresas/auditoria-de-estados-contables/", "/empresas/fiscalizacion-arca/"],
    side_cta=("empresa", None, "¿Tu empresa paga más de lo que debería?", "Diagnóstico sin costo con un especialista en impuestos y auditoría."),
))

# ------------------------------------------------------------------ saldos a favor
PAGES.append(dict(
    path="/empresas/saldos-a-favor/", kind="article", crumbs=[EMP, ("Saldos a favor", "/empresas/saldos-a-favor/")],
    title="Saldos a favor de IIBB e IVA: cómo recuperarlos",
    description="Por qué se acumulan saldos a favor de Ingresos Brutos e IVA, cuánto capital inmovilizan y qué opciones hay para reducirlos, compensarlos o pedir la devolución.",
    h1="Saldos a favor de Ingresos Brutos e IVA: cuánto tenés atrapado y cómo recuperarlo",
    about=["Saldo a favor", "Ingresos Brutos", "IVA", "Retenciones y percepciones"],
    answer=("<p>Un saldo a favor aparece cuando las <strong>retenciones y percepciones</strong> que te practican (bancarias, de clientes y proveedores) superan el impuesto que "
            "realmente debés. Es frecuente en Ingresos Brutos para empresas con márgenes bajos, que venden a grandes agentes de recaudación o que operan en varias provincias. "
            "Se puede atacar pidiendo <strong>exclusión o reducción</strong> de alícuotas, <strong>compensando</strong> con otros impuestos o solicitando la <strong>devolución</strong>, "
            "según la jurisdicción.</p>"),
    body=f"""
<form class="tool" id="calc-saldos" novalidate>
<h2 style="margin:0 0 4px;font-size:23px">Estimador: ¿cuánto saldo a favor vas a acumular?</h2>
<p style="margin:0;color:var(--muted)">Usá promedios mensuales aproximados. Los datos no se guardan.</p>
<div class="row2">
<div><label for="ret">Retenciones + percepciones que te practican por mes</label><input id="ret" type="text" inputmode="numeric" placeholder="Ej.: 4.000.000"></div>
<div><label for="det">Impuesto determinado por mes</label><input id="det" type="text" inputmode="numeric" placeholder="Ej.: 2.500.000"></div>
</div>
<label for="acum">Saldo a favor que ya tenés acumulado (opcional)</label><input id="acum" type="text" inputmode="numeric" placeholder="Ej.: 10.000.000">
<button class="btn" type="submit" style="margin-top:16px">Estimar</button>
<div class="result" hidden aria-live="polite"></div>
</form>
<h2>Por qué se acumulan saldos a favor</h2>
<ul>
<li><strong>Retenciones bancarias</strong> de Ingresos Brutos sobre las acreditaciones (por ejemplo, el sistema SIRCREB), que no distinguen si el ingreso tiene margen.</li>
<li><strong>Percepciones</strong> en compras a grandes proveedores y <strong>retenciones</strong> de grandes clientes.</li>
<li><strong>Alícuotas de padrón</strong> elevadas asignadas por el fisco provincial según su evaluación de riesgo.</li>
<li><strong>Convenio Multilateral:</strong> te retienen en una provincia más de lo que te corresponde tributar ahí según tu coeficiente.</li>
<li>En IVA, <strong>retenciones y percepciones</strong> que superan el débito fiscal y generan saldo de libre disponibilidad.</li>
</ul>
<h2>Qué opciones hay para recuperarlo</h2>
{table(["Herramienta", "Para qué sirve"], [
        ["Exclusión o reducción de retenciones/percepciones", "Evita que el saldo siga creciendo. Cada jurisdicción tiene su trámite y requisitos."],
        ["Revisión de alícuotas de padrón", "Corrige alícuotas que no reflejan tu situación real."],
        ["Compensación", "Usa el saldo para cancelar otras obligaciones del mismo fisco."],
        ["Devolución o repetición", "Pide el reintegro del saldo. Suele requerir documentación y una verificación del fisco."],
        ["Saldo de libre disponibilidad de IVA", "Puede compensarse con otros impuestos nacionales o solicitarse su devolución o transferencia, según el caso."],
    ])}
<p class="note">El saldo técnico de IVA (más crédito fiscal por compras que débito por ventas) en general solo se traslada a períodos siguientes; la devolución está prevista para casos específicos, como exportaciones.</p>
{cta("empresa", "saldos-a-favor", "Armemos tu plan de recupero", "Un especialista en impuestos revisa tus saldos por jurisdicción y te dice qué se puede recuperar y en cuánto tiempo.", button="Quiero un plan de recupero")}
""",
    faqs=[
        ("¿El saldo a favor de Ingresos Brutos se pierde?", "No se pierde, pero inmoviliza capital de trabajo y pierde valor con la inflación. Por eso conviene frenar su crecimiento y recuperarlo lo antes posible."),
        ("¿Se puede pedir que no me retengan Ingresos Brutos?", "Muchas jurisdicciones permiten solicitar la exclusión o reducción de regímenes de recaudación cuando se demuestra que generan saldos a favor sistemáticos. Los requisitos varían por provincia."),
        ("¿Cuánto tarda una devolución?", "Depende del fisco y del monto; puede llevar meses. Por eso suele combinarse con medidas para evitar que el saldo siga creciendo."),
    ],
    sources=[ARCA, COMARB],
    related=["/empresas/convenio-multilateral/", "/empresas/fiscalizacion-arca/", "/empresas/"],
    side_cta=("empresa", "saldos-a-favor", "¿Tenés saldos a favor acumulados?", "Un especialista arma el plan para recuperarlos. Primera reunión sin costo."),
    schema=[{"@type": "WebApplication", "name": "Estimador de saldos a favor de Ingresos Brutos e IVA", "applicationCategory": "FinanceApplication", "operatingSystem": "Web",
             "offers": {"@type": "Offer", "price": "0", "priceCurrency": "ARS"}, "url": C.SITE_URL + "/empresas/saldos-a-favor/"}],
))

# ------------------------------------------------------------------ auditoría
PAGES.append(dict(
    path="/empresas/auditoria-de-estados-contables/", kind="article", crumbs=[EMP, ("Auditoría de estados contables", "/empresas/auditoria-de-estados-contables/")],
    title="Auditoría de estados contables: ¿tu empresa la necesita?",
    description="Cuándo una empresa necesita estados contables auditados en Argentina (IGJ, bancos, SGR, licitaciones, casa matriz), cómo es el proceso y cuándo contratar al auditor.",
    h1="Auditoría de estados contables: cuándo la necesitás y cómo es el proceso",
    about=["Auditoría externa", "Estados contables", "Inspección General de Justicia"],
    answer=("<p>Una auditoría externa es la revisión independiente de los estados contables por un contador público, que emite un <strong>informe con su opinión</strong>. "
            "La necesitan, entre otras, las <strong>sociedades anónimas y SAS</strong> que presentan balances ante la Inspección General de Justicia, las SRL cuyo capital alcanza el monto del "
            "artículo 299 de la Ley General de Sociedades, y cualquier empresa que pida <strong>crédito bancario, avales de SGR</strong>, emita obligaciones negociables, participe en "
            "<strong>licitaciones</strong> o reporte a una <strong>casa matriz</strong>. Conviene contratar al auditor antes del cierre del ejercicio.</p>"),
    body=quiz("test-auditoria", "Test: ¿tu empresa necesita estados contables auditados?", [
        ("¿Es una sociedad anónima (SA) o una SAS?", 1),
        ("¿Es una SRL con un capital social elevado (art. 299 de la Ley General de Sociedades)?", 1),
        ("¿Vas a pedir crédito bancario, un aval de SGR o emitir obligaciones negociables?", 1),
        ("¿Participás o vas a participar en licitaciones públicas o privadas?", 1),
        ("¿La empresa es filial o sucursal de una compañía extranjera?", 1),
        ("¿Estás pensando en vender la empresa o recibir inversión?", 1),
    ], [
        {"min": 0, "title": "Por ahora, quizás no", "text": "Con estas respuestas no aparece una obligación habitual. Igual puede servirte una revisión limitada o una certificación puntual: consultalo antes del cierre."},
        {"min": 1, "title": "Es muy probable que necesites auditoría", "text": "Al menos una situación habitual exige estados contables con informe de auditor. Conviene cotizar y planificar el trabajo antes del cierre del ejercicio."},
    ], "/diagnostico/?perfil=empresa&tema=auditoria", "Cotizar la auditoría") + f"""
<p class="note">El test es orientativo. Las obligaciones dependen del tipo societario, la jurisdicción de inscripción y los requisitos de cada banco, organismo o casa matriz.</p>
<h2>Quién suele necesitar estados contables auditados</h2>
{table(["Situación", "Qué piden"], [
        ["Sociedades anónimas y SAS inscriptas en la IGJ", "Presentar los estados contables con el informe del auditor."],
        ["Sociedades del art. 299 de la Ley 19.550 (control permanente)", "Estados contables auditados y fiscalización estatal permanente."],
        ["SRL con capital igual o superior al monto del art. 299 inc. 2", "Remitir sus estados contables al Registro Público."],
        ["Crédito bancario, SGR u obligaciones negociables", "Balances auditados de uno o más ejercicios."],
        ["Licitaciones", "Estados contables con informe de auditor, según el pliego."],
        ["Filiales de empresas extranjeras", "Reporting a casa matriz, a menudo bajo NIIF."],
        ["Venta de la empresa o ingreso de inversores", "Auditoría o due diligence contable e impositiva."],
    ])}
<h2>Cómo es el proceso de auditoría</h2>
<ol>
<li><strong>Propuesta y planificación</strong> (antes del cierre): alcance, honorarios, cronograma.</li>
<li><strong>Revisión preliminar:</strong> control interno, riesgos, procedimientos intermedios.</li>
<li><strong>Trabajo de cierre:</strong> inventarios, confirmaciones de saldos con bancos, clientes y proveedores.</li>
<li><strong>Informe del auditor</strong> con su opinión sobre los estados contables.</li>
</ol>
<p>Las sociedades por acciones suelen aprobar sus estados contables en asamblea dentro de los cuatro meses posteriores al cierre, por lo que el auditor debería estar contratado antes.</p>
{cta("empresa", "auditoria", "Cotizá la auditoría de tu empresa", "Te conectamos con un estudio especializado en auditoría para empresas medianas. Propuesta sin compromiso.", button="Cotizar auditoría")}
<h2>Cuándo cambiar de auditor</h2>
<ul><li>El informe llega tarde y complica la asamblea o el banco.</li><li>No hay recomendaciones útiles de control interno.</li><li>La empresa creció y necesita NIIF, consolidación o reporting internacional.</li></ul>""",
    faqs=[
        ("¿Todas las empresas tienen que auditar sus balances?", "No todas. Depende del tipo societario, la jurisdicción y de quién te pida los estados contables (IGJ, bancos, licitaciones, casa matriz). Un especialista puede confirmarlo en tu caso."),
        ("¿Cuándo conviene contratar al auditor?", "Antes del cierre del ejercicio. Para cierres al 31 de diciembre, el segundo semestre es el momento de pedir propuestas."),
        ("¿Una SAS necesita auditor?", "En la jurisdicción de la IGJ, las SAS presentan sus estados contables junto con el informe del auditor. En otras provincias conviene verificar la normativa local."),
    ],
    sources=[LGS, IGJ, BO],
    related=["/empresas/como-elegir-estudio-contable/", "/empresas/fiscalizacion-arca/", "/empresas/"],
    side_cta=("empresa", "auditoria", "¿Necesitás balance auditado?", "Cotizá la auditoría con un estudio especializado. Sin compromiso."),
))

# ------------------------------------------------------------------ fiscalización
PAGES.append(dict(
    path="/empresas/fiscalizacion-arca/", kind="article", crumbs=[EMP, ("Fiscalización de ARCA", "/empresas/fiscalizacion-arca/")],
    title="Fiscalización de ARCA: checklist para tu empresa",
    description="Checklist de 8 puntos para saber si tu empresa resistiría una fiscalización de ARCA y qué hacer si recibís un requerimiento o una inspección.",
    h1="¿Tu empresa resistiría una fiscalización de ARCA? Checklist de riesgo",
    about=["Fiscalización", "ARCA", "Requerimientos fiscales"],
    answer=("<p>Las fiscalizaciones hoy empiezan casi siempre por <strong>cruces sistémicos</strong>: ARCA compara tu facturación electrónica, el Libro IVA Digital, las acreditaciones bancarias, "
            "las cargas sociales y lo que informan tus clientes y proveedores. Las contingencias más comunes son diferencias entre esas fuentes, gastos sin respaldo y personal mal registrado. "
            "Si recibís un requerimiento, respondé dentro del plazo y con asesoramiento.</p>"),
    body=quiz("test-fiscalizacion", "Checklist: respondé por tu empresa", [
        ("¿Conciliás todos los meses la facturación electrónica con el Libro IVA Digital?", 1),
        ("¿Las acreditaciones bancarias coinciden con las ventas declaradas?", 1),
        ("¿Alguien revisa el Domicilio Fiscal Electrónico al menos una vez por semana?", 1),
        ("¿Todos los gastos deducidos tienen comprobante válido y respaldo?", 1),
        ("¿Todo el personal está registrado y el F.931 coincide con la nómina real?", 1),
        ("¿Conciliás las retenciones y percepciones sufridas con lo que informan los agentes?", 1),
        ("¿Las operaciones con empresas vinculadas están documentadas?", 1),
        ("¿Los libros contables están al día?", 1),
    ], [
        {"min": 0, "title": "Riesgo bajo", "text": "Tenés los controles básicos en orden. Una revisión preventiva anual ayuda a mantenerlo así."},
        {"min": 2, "title": "Riesgo medio", "text": "Hay puntos sin control que suelen generar ajustes en una fiscalización. Conviene corregirlos antes de que lleguen."},
        {"min": 4, "title": "Riesgo alto", "text": "Varias áreas clave no tienen control. Una revisión preventiva puede evitar ajustes, intereses y multas."},
    ], "/diagnostico/?perfil=empresa&tema=fiscalizacion", "Pedir una revisión preventiva", invert=True) + f"""
<h2>Qué hacer si recibís un requerimiento de ARCA</h2>
<ol>
<li><strong>No lo ignores:</strong> los plazos corren desde la notificación en el Domicilio Fiscal Electrónico.</li>
<li><strong>Identificá qué piden</strong> y qué período abarca.</li>
<li><strong>Respondé solo lo que se pide</strong>, con documentación ordenada y coherente.</li>
<li><strong>Si no llegás con el plazo</strong>, pedí una prórroga por escrito antes del vencimiento.</li>
<li><strong>Consultá a un especialista</strong> antes de rectificar declaraciones juradas.</li>
</ol>
{cta("empresa", "fiscalizacion", "¿Te llegó un requerimiento o una inspección?", "Un especialista en impuestos revisa el caso y arma la respuesta. Los plazos son cortos: escribinos hoy.", button="Necesito ayuda con ARCA")}""",
    faqs=[
        ("¿Cómo me notifica ARCA una fiscalización?", "Generalmente a través del Domicilio Fiscal Electrónico, que es obligatorio. Por eso es clave revisarlo seguido."),
        ("¿Qué pasa si no respondo un requerimiento?", "Puede derivar en multas formales y en una fiscalización más amplia, además de la pérdida de oportunidades para explicar las diferencias."),
    ],
    sources=[ARCA],
    related=["/empresas/saldos-a-favor/", "/empresas/precios-de-transferencia/", "/empresas/"],
    side_cta=("empresa", "fiscalizacion", "Revisión preventiva para tu empresa", "Detectá contingencias antes que ARCA. Primera reunión sin costo."),
))

# ------------------------------------------------------------------ convenio multilateral
PAGES.append(dict(
    path="/empresas/convenio-multilateral/", kind="article", crumbs=[EMP, ("Convenio Multilateral", "/empresas/convenio-multilateral/")],
    title="Convenio Multilateral de Ingresos Brutos: guía práctica",
    description="Qué es el Convenio Multilateral, cuándo corresponde, cómo se calcula el coeficiente unificado y qué errores generan saldos a favor o ajustes en Ingresos Brutos.",
    h1="Convenio Multilateral de Ingresos Brutos: cómo funciona y errores comunes",
    about=["Convenio Multilateral", "Ingresos Brutos"],
    answer=("<p>El Convenio Multilateral reparte la base imponible de <strong>Ingresos Brutos</strong> entre las provincias cuando una empresa vende o presta servicios en más de una. "
            "En el <strong>régimen general</strong> se arma un coeficiente por provincia: 50% según dónde se generan los ingresos y 50% según dónde se realizan los gastos. "
            "Hay regímenes especiales para actividades como construcción, transporte, seguros o profesiones liberales. Se declara mensualmente y con una declaración jurada anual.</p>"),
    body=f"""
<h2>Cuándo corresponde</h2>
<p>Cuando la actividad se desarrolla en más de una jurisdicción: por ejemplo, una empresa con sede en CABA que vende a clientes de Córdoba y Santa Fe, con gastos en esas provincias (viajantes, depósitos, fletes, publicidad local).</p>
<h2>Cómo se calcula el coeficiente (régimen general)</h2>
{table(["Componente", "Peso", "Cómo se toma"], [["Ingresos", "50%", "Proporción de ingresos atribuibles a cada provincia en el ejercicio anterior"], ["Gastos", "50%", "Proporción de gastos soportados en cada provincia en el ejercicio anterior"]])}
<p>El coeficiente unificado de cada provincia se aplica a la base imponible del mes. Cada provincia aplica después su propia alícuota.</p>
<h2>Errores que generan saldos a favor o ajustes</h2>
<ul>
<li>Coeficientes mal calculados o sin actualizar al inicio del ejercicio.</li>
<li>No incluir gastos computables o incluir gastos que no lo son.</li>
<li>Retenciones bancarias concentradas en una provincia con coeficiente bajo.</li>
<li>Alta tardía en una jurisdicción donde ya hay actividad.</li>
</ul>
{cta("empresa", "convenio-multilateral", "¿Operás en varias provincias?", "Un especialista revisa tus coeficientes y saldos por jurisdicción.", button="Revisar mi Convenio Multilateral")}""",
    faqs=[
        ("¿Dónde se presentan las declaraciones del Convenio Multilateral?", "A través del sistema SIFERE de la Comisión Arbitral, con declaraciones mensuales y una declaración jurada anual."),
        ("¿El Convenio Multilateral cambia la alícuota?", "No. Reparte la base imponible entre provincias; cada provincia aplica su propia alícuota sobre la parte que le corresponde."),
    ],
    sources=[COMARB],
    related=["/empresas/saldos-a-favor/", "/empresas/fiscalizacion-arca/"],
    side_cta=("empresa", "convenio-multilateral", "Revisá tus coeficientes", "Errores en el Convenio Multilateral generan saldos a favor y ajustes. Consultá sin costo."),
))

# ------------------------------------------------------------------ precios de transferencia
PAGES.append(dict(
    path="/empresas/precios-de-transferencia/", kind="article", crumbs=[EMP, ("Precios de transferencia", "/empresas/precios-de-transferencia/")],
    title="Precios de transferencia 2026: umbrales de la RG 5903",
    description="Qué son los precios de transferencia, quién debe presentar el F.2668 y el estudio de precios de transferencia con los umbrales de la RG ARCA 5903/2026.",
    h1="Precios de transferencia: quién está obligado y umbrales vigentes",
    about=["Precios de transferencia", "Impuesto a las Ganancias", "Operaciones internacionales"],
    answer=("<p>Las operaciones con <strong>empresas vinculadas del exterior</strong> o con sujetos en jurisdicciones no cooperantes o de baja tributación deben pactarse a valores "
            "de mercado. La <strong>RG ARCA 5903/2026</strong> (Boletín Oficial del 30/9/2026) unificó el régimen y elevó los umbrales: el <strong>Estudio de Precios de Transferencia</strong> "
            "corresponde cuando esas operaciones superan <strong>$3.000 millones</strong> en conjunto o <strong>$600 millones</strong> en una operación individual en el ejercicio.</p>"),
    body=f"""
<h2>Umbrales principales (RG 5903/2026)</h2>
{table(["Obligación", "Cuándo corresponde"], [
        ["Declaración jurada F.2668", "Operaciones sujetas a precios de transferencia por más de $1.500 millones en conjunto o $300 millones individualmente"],
        ["Estudio de Precios de Transferencia", "Operaciones con vinculadas por más de $3.000 millones en conjunto o $600 millones individualmente"],
        ["Informe Maestro", "Grupos con ingresos consolidados de más de $500.000 millones, además de los montos de operaciones"],
    ], caption="Resumen orientativo. Verificá alcance, excepciones y plazos en el texto de la resolución.")}
<p class="note">La RG 5903/2026 reemplazó a las RG 4717 y 5010. Si tu empresa estaba obligada con los umbrales anteriores, puede haber dejado de estarlo (o no): conviene revisarlo con el cierre de cada ejercicio.</p>
<h2>Qué se considera vinculación</h2>
<p>En términos generales, hay vinculación cuando una empresa participa en el capital, la dirección o el control de otra, o cuando ambas están bajo control común. También alcanzan las operaciones con sujetos en jurisdicciones no cooperantes o de baja o nula tributación, aunque no sean vinculados.</p>
<h2>Riesgos de no cumplir</h2>
<ul><li>Ajustes de precios con impacto en Ganancias.</li><li>Multas por falta de presentación, que la reforma de la Ley de Inocencia Fiscal actualizó.</li><li>Más exposición en una fiscalización.</li></ul>
{cta("empresa", "precios-transferencia", "¿Tenés operaciones con vinculadas del exterior?", "Un especialista revisa si estás alcanzado con los nuevos umbrales y qué tenés que presentar.", button="Revisar mi caso")}""",
    faqs=[
        ("¿Qué cambió con la RG 5903/2026?", "Unificó en un solo texto los regímenes de precios de transferencia y operaciones internacionales, reemplazó a las RG 4717 y 5010 y elevó los montos a partir de los cuales hay que presentar información."),
        ("¿Una pyme puede estar alcanzada por precios de transferencia?", "Sí, si opera con vinculadas del exterior o con jurisdicciones no cooperantes o de baja tributación por montos que superan los umbrales."),
    ],
    sources=[("Boletín Oficial — RG ARCA 5903/2026", "https://www.boletinoficial.gob.ar/"), ARCA],
    related=["/empresas/fiscalizacion-arca/", "/empresas/como-elegir-estudio-contable/"],
    side_cta=("empresa", "precios-transferencia", "¿Estás alcanzado por los nuevos umbrales?", "Revisión sin costo con un especialista en impuestos internacionales."),
))

# ------------------------------------------------------------------ cómo elegir estudio
PLIEGO = """PEDIDO DE PROPUESTA — SERVICIOS DE IMPUESTOS Y AUDITORÍA

1. Datos de la empresa
- Razón social y tipo societario:
- Actividad principal:
- Facturación anual aproximada:
- Cantidad de empleados:
- Provincias donde opera:
- Fecha de cierre de ejercicio:
- Operaciones con el exterior / vinculadas: sí / no

2. Servicios requeridos
- Auditoría de estados contables (ejercicio que cierra el __/__/____)
- Liquidación de impuestos nacionales (IVA, Ganancias)
- Ingresos Brutos / Convenio Multilateral
- Precios de transferencia
- Revisión de saldos a favor
- Atención de fiscalizaciones y requerimientos
- Otros:

3. Qué pedimos en la propuesta
- Equipo asignado (socio responsable, gerente, matrículas)
- Experiencia en empresas similares
- Cronograma de trabajo y fechas de entrega
- Honorarios, forma de ajuste y servicios no incluidos
- Canal y plazo de respuesta a consultas
- Referencias de clientes

4. Plazo para enviar la propuesta: __/__/____
Contacto: nombre, cargo, email, teléfono"""

PAGES.append(dict(
    path="/empresas/como-elegir-estudio-contable/", kind="article", crumbs=[EMP, ("Cómo elegir estudio contable", "/empresas/como-elegir-estudio-contable/")],
    title="Cómo elegir estudio contable para tu empresa (+ plantilla)",
    description="Criterios para elegir o cambiar de estudio contable y de auditoría, preguntas para la entrevista y una plantilla de pedido de propuesta para comparar estudios.",
    h1="Cómo elegir un estudio contable para tu empresa (con plantilla de pedido de propuesta)",
    about=["Estudio contable", "Auditoría", "Selección de proveedores"],
    answer=("<p>Para elegir estudio contable, compará: <strong>especialización</strong> en empresas de tu tamaño y sector, <strong>equipo asignado</strong> (quién firma y quién trabaja), "
            "capacidad en <strong>impuestos y auditoría</strong> (Convenio Multilateral, precios de transferencia, NIIF si tenés casa matriz), <strong>tiempos de respuesta</strong> y "
            "<strong>honorarios con alcance claro</strong>. Pedí propuestas por escrito con la misma plantilla para comparar en igualdad de condiciones.</p>"),
    body=f"""
<h2>Criterios para comparar estudios</h2>
{table(["Criterio", "Qué preguntar"], [
        ["Especialización", "¿Qué clientes de mi tamaño y sector atienden?"],
        ["Equipo", "¿Quién es el socio responsable? ¿Quién hace el trabajo diario?"],
        ["Alcance", "¿Qué incluye el abono y qué se cobra aparte?"],
        ["Impuestos complejos", "¿Tienen experiencia en Convenio Multilateral, saldos a favor y precios de transferencia?"],
        ["Auditoría", "¿Pueden auditar bajo normas locales y NIIF? ¿Cuál es su cronograma de cierre?"],
        ["Comunicación", "¿Por qué canal y en qué plazo responden?"],
        ["Tecnología", "¿Cómo intercambian documentación? ¿Dan reportes periódicos?"],
    ])}
<h2>Plantilla de pedido de propuesta</h2>
<p>Copiala, completala y enviala a los estudios que quieras comparar.</p>
<div class="tool"><pre id="pliego" style="white-space:pre-wrap;font-family:inherit;font-size:15px;margin:0">{PLIEGO}</pre>
<button type="button" class="btn sec" data-copy="#pliego" style="margin-top:14px">Copiar plantilla</button></div>
{cta("empresa", "cambiar-estudio", "¿Querés recibir una propuesta?", "Te conectamos con un estudio aliado especializado en impuestos y auditoría para empresas medianas.", button="Recibir una propuesta")}""",
    faqs=[
        ("¿Conviene tener el mismo estudio para impuestos y auditoría?", "Puede ser práctico, pero la auditoría exige independencia: el estudio no debería auditar registros o decisiones que él mismo preparó. Muchos estudios separan los equipos."),
        ("¿Cada cuánto conviene revisar al estudio contable?", "Una vez por año, al cierre del ejercicio, es un buen momento para evaluar servicio, tiempos y honorarios."),
    ],
    sources=[LGS],
    related=["/empresas/auditoria-de-estados-contables/", "/contador/cuanto-cobra-un-contador/"],
    side_cta=("empresa", "cambiar-estudio", "Compará propuestas", "Recibí una propuesta de un estudio especializado en empresas medianas."),
))
