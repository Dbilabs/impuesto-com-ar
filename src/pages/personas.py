"""Páginas para personas: monotributo y contador."""
from lib import MONO, money, cta, mono_table, mono_calc, quiz, table, ARCA, ARCA_MONO, ARCA_CAT, ARCA_EXCL, LEY_MONO, BO
import config as C

A, K = MONO["categorias"][0], MONO["categorias"][-1]
VIG = MONO["vigencia_texto"]
RECAT = MONO["proxima_recategorizacion"]
MONO_CRUMB = ("Monotributo", "/monotributo/")
CONT_CRUMB = ("Contador", "/contador/tu-contador-lo-hace-bien/")
SIDE_MONO = ("persona", "monotributo-categoria", "¿Estás en la categoría correcta?", "Un contador revisa tu monotributo gratis y te dice si pagás de más. Sin pedirte la clave fiscal.")

PAGES = []

# ------------------------------------------------------------------ hub
PAGES.append(dict(
    path="/monotributo/", kind="article", crumbs=[MONO_CRUMB],
    title="Monotributo 2026: categorías, cuotas y recategorización",
    description=f"Guía del monotributo en Argentina: tabla de categorías vigente, cuánto pagás por mes, cuándo recategorizarte ({RECAT}) y cómo evitar la exclusión.",
    h1="Monotributo: guía completa para 2026",
    about=["Monotributo", "Régimen Simplificado para Pequeños Contribuyentes", "ARCA"],
    answer=(f"<p>El monotributo es el régimen simplificado de ARCA para pequeños contribuyentes: pagás una <strong>cuota mensual única</strong> que incluye "
            f"impuesto, jubilación y obra social. Hay 11 categorías, de la A a la K. Con la tabla vigente {VIG}, la categoría A llega hasta "
            f"<strong>{money(A['tope'], True)}</strong> de ingresos anuales con una cuota de <strong>{money(A['servicios'], True)}</strong>, y la K hasta "
            f"<strong>{money(K['tope'], True)}</strong>. La cuota vence el día 20 de cada mes y la próxima recategorización vence el <strong>{RECAT}</strong>.</p>"),
    body=f"""
<h2>Lo esencial en 5 puntos</h2>
<ol>
<li><strong>Quién puede ser monotributista:</strong> personas que venden bienes o prestan servicios, y algunas sociedades, mientras sus ingresos de los últimos 12 meses no superen el tope de la categoría K.</li>
<li><strong>Qué pagás:</strong> una cuota mensual con tres componentes: impuesto integrado, aporte jubilatorio (SIPA) y obra social.</li>
<li><strong>Cómo se define tu categoría:</strong> por tus ingresos brutos de los últimos 12 meses y, si tenés local, por superficie, energía consumida y alquileres. En venta de bienes también cuenta el precio unitario máximo.</li>
<li><strong>Cuándo se revisa:</strong> dos veces por año (recategorización de enero y de julio). Si no lo hacés y corresponde, ARCA puede recategorizarte de oficio.</li>
<li><strong>Qué factura emitís:</strong> factura C. Tus clientes no pueden computar IVA por tus compras.</li>
</ol>
<h2>Tabla de categorías vigente</h2>
{mono_table()}
<p>¿Querés saber cuál te corresponde? Usá la <a href="/monotributo/categorias/">calculadora de categorías</a>.</p>
{cta("persona", "monotributo-categoria", "¿Pagás de más de monotributo?", "Si tu facturación bajó o nadie te recategorizó, quizás estás en una categoría más cara. Un contador lo revisa gratis.")}
<h2>Fechas que no te podés olvidar</h2>
{table(["Qué", "Cuándo"], [["Pago de la cuota mensual", "Hasta el día 20 de cada mes (o el hábil siguiente)"], ["Recategorización de enero", f"Vence el {RECAT} (mira enero–diciembre)"], ["Recategorización de julio", "Vence a principios de agosto (mira julio–junio)"], ["Actualización de la tabla", "Febrero y agosto, según la inflación del semestre"]])}
<h2>Guías del monotributo</h2>
<ul>
<li><a href="/monotributo/categorias/">Categorías y cuotas 2026 + calculadora</a></li>
<li><a href="/monotributo/recategorizacion/">Recategorización: cuándo y cómo hacerla</a></li>
<li><a href="/monotributo/exclusion/">Exclusión del monotributo: causas y qué hacer</a></li>
<li><a href="/monotributo/monotributo-o-responsable-inscripto/">¿Monotributo o responsable inscripto?</a></li>
</ul>""",
    faqs=[
        ("¿Cuánto se paga de monotributo en 2026?", f"Con la tabla vigente {VIG}, la cuota va de {money(A['servicios'], True)} (categoría A) a {money(K['servicios'], True)} (categoría K en servicios) y {money(K['venta'], True)} (K en venta de bienes)."),
        ("¿Hasta qué día se paga el monotributo?", "Hasta el día 20 de cada mes. Si cae en feriado o fin de semana, pasa al primer día hábil siguiente."),
        ("¿Cuándo es la próxima recategorización?", f"La recategorización de enero vence el {RECAT} y toma los ingresos de enero a diciembre de 2026."),
        ("¿El monotributo incluye obra social?", "Sí. La cuota incluye el aporte a la obra social que elegís, además del impuesto integrado y el aporte jubilatorio. Hay excepciones, por ejemplo para quienes ya aportan por relación de dependencia."),
    ],
    sources=[ARCA_MONO, ARCA_CAT, LEY_MONO],
    related=["/monotributo/categorias/", "/monotributo/recategorizacion/", "/monotributo/exclusion/", "/contador/tu-contador-lo-hace-bien/"],
    side_cta=SIDE_MONO,
))

# ------------------------------------------------------------------ categorías + calculadora
PAGES.append(dict(
    path="/monotributo/categorias/", kind="article", crumbs=[MONO_CRUMB, ("Categorías y cuotas", "/monotributo/categorias/")],
    title="Categorías del monotributo 2026: tabla y calculadora",
    description="Tabla oficial de categorías del monotributo vigente hasta enero 2027: topes de facturación y cuota mensual de la A a la K. Calculá tu categoría.",
    h1="Categorías del monotributo 2026: tabla oficial y calculadora",
    about=["Categorías del Monotributo", "Monotributo"],
    answer=(f"<p>Hay 11 categorías. Con los valores vigentes {VIG}, la <strong>categoría A</strong> llega hasta {money(A['tope'], True)} de ingresos en 12 meses "
            f"y paga {money(A['servicios'], True)} por mes; la <strong>categoría K</strong> llega hasta {money(K['tope'], True)} y paga {money(K['servicios'], True)} "
            f"en servicios o {money(K['venta'], True)} en venta de bienes. Si superás el tope de la K, quedás excluido del régimen.</p>"),
    body=f"""
{mono_calc()}
<h2>Tabla completa de categorías y cuotas</h2>
{mono_table()}
<p class="note">Los valores se actualizan dos veces por año (febrero y agosto) según la inflación del semestre anterior. Esta tabla rige hasta el 31 de enero de 2027.</p>
<h2>Cómo se determina tu categoría</h2>
<p>ARCA mira los <strong>últimos 12 meses</strong> y te ubica en la categoría más alta que alcances por cualquiera de estos parámetros:</p>
<ul>
<li><strong>Ingresos brutos</strong> facturados (lo que figura en tus comprobantes, no lo cobrado).</li>
<li><strong>Superficie afectada</strong> a la actividad, si tenés local.</li>
<li><strong>Energía eléctrica</strong> consumida en el local.</li>
<li><strong>Alquileres devengados</strong> por el local.</li>
<li>En venta de bienes, el <strong>precio unitario máximo</strong> de lo que vendés.</li>
</ul>
<p>Si trabajás desde tu casa sin local afectado, en la práctica tu categoría la define la facturación.</p>
<h2>Ejemplo</h2>
<p>Una diseñadora que facturó $28.000.000 en los últimos 12 meses por servicios supera el tope de la C ({money(MONO['categorias'][2]['tope'], True)}) y queda en la <strong>categoría D</strong>, con una cuota de {money(MONO['categorias'][3]['servicios'], True)} por mes. Si sigue pagando la C, en la próxima recategorización debe subir; si no lo hace, ARCA puede recategorizarla de oficio.</p>
{cta("persona", "monotributo-categoria", "¿Querés confirmar tu categoría?", "Un contador revisa todos los parámetros (no solo la facturación) y te dice qué hacer antes de la recategorización.")}
""",
    faqs=[
        ("¿Cuál es la categoría más baja del monotributo?", f"La A: hasta {money(A['tope'], True)} de ingresos anuales y una cuota mensual de {money(A['servicios'], True)} ({VIG})."),
        ("¿Cuál es el tope máximo del monotributo?", f"El de la categoría K: {money(K['tope'], True)} de ingresos en los últimos 12 meses. Superarlo es causal de exclusión."),
        ("¿Los prestadores de servicios pueden llegar a la categoría K?", "Sí. Desde la reforma de la Ley 27.743, las categorías I, J y K también están disponibles para servicios, con cuotas distintas a las de venta de bienes."),
        ("¿La facturación se mide por año calendario?", "No: se miran los últimos 12 meses anteriores a cada recategorización. En la de enero coincide con el año calendario (enero a diciembre)."),
    ],
    sources=[ARCA_CAT, LEY_MONO],
    related=["/monotributo/recategorizacion/", "/monotributo/exclusion/", "/monotributo/monotributo-o-responsable-inscripto/"],
    side_cta=SIDE_MONO,
    schema=[{"@type": "WebApplication", "name": "Calculadora de categoría del monotributo", "applicationCategory": "FinanceApplication",
             "operatingSystem": "Web", "offers": {"@type": "Offer", "price": "0", "priceCurrency": "ARS"}, "url": C.SITE_URL + "/monotributo/categorias/"},
            {"@type": "Dataset", "name": "Categorías y cuotas del Monotributo (Argentina)", "description": f"Topes de ingresos brutos y cuotas mensuales del monotributo, vigentes {VIG}.",
             "temporalCoverage": f"{MONO['vigencia_desde']}/{MONO['vigencia_hasta']}", "creator": {"@id": C.SITE_URL + "/#org"},
             "isBasedOn": MONO["fuente"], "license": "https://creativecommons.org/licenses/by/4.0/"}],
))

# ------------------------------------------------------------------ recategorización
PAGES.append(dict(
    path="/monotributo/recategorizacion/", kind="article", crumbs=[MONO_CRUMB, ("Recategorización", "/monotributo/recategorizacion/")],
    title=f"Recategorización del monotributo: vence el {RECAT}",
    description=f"Cuándo y cómo recategorizarte en el monotributo. La próxima vence el {RECAT}. Qué pasa si no lo hacés y cómo apelar una recategorización de oficio.",
    h1="Recategorización del monotributo: fechas, paso a paso y qué pasa si no la hacés",
    about=["Recategorización del Monotributo"],
    answer=(f"<p>La recategorización es la revisión semestral de tu categoría según los últimos 12 meses. Se hace en <strong>enero</strong> (la próxima vence el "
            f"<strong>{RECAT}</strong> y mira enero–diciembre de 2026) y en <strong>julio</strong> (vence a principios de agosto). Solo es obligatoria si cambia tu "
            "categoría. Si no la hacés y correspondía, ARCA puede recategorizarte de oficio y aplicar una multa.</p>"),
    body=f"""
<h2>Quién tiene que recategorizarse</h2>
<ul>
<li>Quien, según sus ingresos y demás parámetros de los últimos 12 meses, quedó en una categoría <strong>distinta</strong> a la actual (más alta o más baja).</li>
<li>No hace falta si la categoría no cambia.</li>
<li>Si empezaste la actividad hace menos de 6 meses, todavía no te recategorizás.</li>
</ul>
<h2>Paso a paso</h2>
<ol>
<li>Sumá lo que <strong>facturaste</strong> en los últimos 12 meses (lo emitido, aunque no lo hayas cobrado).</li>
<li>Revisá superficie, energía y alquileres si tenés local.</li>
<li>Compará con la <a href="/monotributo/categorias/">tabla vigente</a> o usá la calculadora.</li>
<li>Entrá con clave fiscal al servicio Monotributo de ARCA (web o app) y elegí “Recategorizarme”.</li>
<li>Descargá la nueva credencial de pago. La nueva cuota rige desde el mes siguiente.</li>
</ol>
<h2>Si ARCA te recategoriza de oficio</h2>
<p>Cuando ARCA detecta que te correspondía otra categoría, notifica la recategorización de oficio en tu <strong>Domicilio Fiscal Electrónico</strong> dentro de los 10 días hábiles posteriores al vencimiento. Tenés <strong>15 días</strong> desde la notificación para apelar desde “Presentaciones digitales”. Además de la diferencia de cuota, puede corresponder una multa.</p>
<p class="note">Revisá tu Domicilio Fiscal Electrónico seguido: los plazos corren aunque no hayas leído la notificación.</p>
{cta("persona", "monotributo-categoria", "¿Te toca recategorizarte?", f"Antes del {RECAT}, un contador puede revisar tu caso y evitarte una recategorización de oficio.")}
<h2>Errores comunes</h2>
<ul>
<li>Sumar lo <em>cobrado</em> en vez de lo <em>facturado</em>.</li>
<li>Olvidar facturas emitidas desde otro punto de venta o desde la app.</li>
<li>No mirar los parámetros físicos (superficie, energía, alquileres).</li>
<li>Bajar de categoría sin chequear que todos los parámetros lo permiten.</li>
</ul>""",
    faqs=[
        ("¿Hasta cuándo hay tiempo para recategorizarse?", f"La recategorización de enero vence el {RECAT}. La de julio vence a principios de agosto."),
        ("¿Qué pasa si no me recategorizo?", "Si correspondía un cambio, ARCA puede recategorizarte de oficio, cobrarte la diferencia con intereses y aplicar una multa."),
        ("¿Puedo bajar de categoría?", "Sí. Si tus ingresos y demás parámetros de los últimos 12 meses entran en una categoría más baja, podés recategorizarte hacia abajo y pagar una cuota menor."),
        ("¿Cuánto tiempo tengo para apelar una recategorización de oficio?", "15 días desde la notificación en tu Domicilio Fiscal Electrónico, mediante Presentaciones Digitales."),
    ],
    sources=[ARCA_MONO, ARCA_CAT, LEY_MONO],
    related=["/monotributo/categorias/", "/monotributo/exclusion/", "/calendario-fiscal/"],
    side_cta=SIDE_MONO,
))

# ------------------------------------------------------------------ exclusión
PAGES.append(dict(
    path="/monotributo/exclusion/", kind="article", crumbs=[MONO_CRUMB, ("Exclusión", "/monotributo/exclusion/")],
    title="Exclusión del monotributo: causas, apelación y reingreso",
    description="Por qué ARCA te puede excluir del monotributo, qué pasa después (IVA y Ganancias) y cómo apelar en 15 días. Señales de alerta para actuar a tiempo.",
    h1="Exclusión del monotributo: por qué pasa y qué hacer",
    about=["Exclusión del Monotributo", "ARCA"],
    answer=("<p>ARCA excluye del monotributo a quien deja de cumplir los requisitos del régimen; la causa más común es <strong>superar el tope de ingresos de la "
            f"categoría K</strong> ({money(K['tope'], True)} en 12 meses). La exclusión te da de alta en <strong>IVA y Ganancias</strong> desde el día siguiente. "
            "Tenés <strong>15 días</strong> desde la notificación para apelar. Como regla, no podés volver al monotributo hasta pasados 3 años calendario.</p>"),
    body=f"""
<h2>Causas de exclusión más frecuentes</h2>
<ul>
<li>Ingresos brutos de los últimos 12 meses por encima del tope de la categoría K.</li>
<li>Superar los parámetros máximos de superficie, energía o alquileres.</li>
<li>En venta de bienes, vender a un precio unitario superior al máximo permitido.</li>
<li>Gastos personales, compras o depósitos bancarios incompatibles con los ingresos declarados.</li>
<li>Compras y gastos de la actividad que superan los porcentajes de ingresos que fija la ley.</li>
<li>Importar bienes o servicios para revenderlos.</li>
<li>Tener más de tres actividades simultáneas o más de tres unidades de explotación.</li>
<li>Falta de pago prolongada: ARCA puede dar de baja automáticamente tras 10 meses consecutivos sin pagar.</li>
</ul>
<p>La lista completa está en el artículo 20 de la Ley 24.977 y en el sitio de ARCA.</p>
<h2>Qué pasa si te excluyen</h2>
<ol>
<li>Pasás al régimen general: <strong>IVA, Ganancias y aportes de autónomos</strong>.</li>
<li>Tenés que empezar a emitir factura A o B y presentar declaraciones juradas.</li>
<li>No podés reingresar al monotributo hasta que pasen 3 años calendario (salvo excepciones puntuales previstas por la ley).</li>
</ol>
<h2>Cómo apelar</h2>
<p>La exclusión se notifica en el Domicilio Fiscal Electrónico. Desde la notificación tenés <strong>15 días</strong> para presentar el recurso desde “Presentaciones digitales”. Conviene revisar con un contador el período observado, el parámetro que ARCA considera excedido y de dónde sacó el dato: muchas exclusiones se basan en información que se puede explicar (transferencias entre cuentas propias, préstamos, reintegros).</p>
{cta("persona", "exclusion", "¿Te llegó una exclusión o una intimación?", "Los plazos son cortos. Un contador puede revisar tu caso hoy y preparar la apelación.", button="Necesito ayuda urgente")}
<h2>Señales de alerta para actuar antes</h2>
<ul>
<li>Te acercás al tope de la K o estás en la J o la K.</li>
<li>Recibís transferencias que no son ingresos de la actividad.</li>
<li>Tus consumos con tarjeta son altos en relación con lo que facturás.</li>
<li>Compraste un auto o un inmueble recientemente.</li>
</ul>""",
    faqs=[
        ("¿Cuánto tiempo tengo para apelar una exclusión del monotributo?", "15 días desde la notificación en el Domicilio Fiscal Electrónico."),
        ("¿Puedo volver al monotributo después de una exclusión?", "Como regla general, recién después de 3 años calendario. La Ley 27.743 habilitó un reingreso por única vez para ciertos excluidos desde 2024; un contador puede confirmar si aplica a tu caso."),
        ("¿Me pueden excluir por transferencias bancarias?", "ARCA cruza depósitos y acreditaciones con tus ingresos declarados. Si no son ingresos de la actividad (por ejemplo, dinero propio), conviene tener documentación que lo demuestre."),
    ],
    sources=[ARCA_EXCL, LEY_MONO],
    related=["/monotributo/monotributo-o-responsable-inscripto/", "/monotributo/recategorizacion/", "/monotributo/categorias/"],
    side_cta=("persona", "exclusion", "¿Riesgo de exclusión?", "Contanos tu caso y un contador te dice cómo protegerte. Gratis y sin compromiso."),
))

# ------------------------------------------------------------------ monotributo vs RI
PAGES.append(dict(
    path="/monotributo/monotributo-o-responsable-inscripto/", kind="article", crumbs=[MONO_CRUMB, ("Monotributo o responsable inscripto", "/monotributo/monotributo-o-responsable-inscripto/")],
    title="¿Monotributo o responsable inscripto? Cuándo conviene cada uno",
    description="Diferencias entre monotributo y responsable inscripto: impuestos, facturación, costos y en qué casos conviene pasarse al régimen general.",
    h1="¿Monotributo o responsable inscripto? Cuándo conviene cada uno",
    about=["Monotributo", "Responsable Inscripto", "IVA", "Impuesto a las Ganancias"],
    answer=("<p>El <strong>monotributo</strong> conviene cuando facturás por debajo de los topes y tenés pocos costos: pagás una cuota fija y tenés poca carga administrativa. "
            "Como <strong>responsable inscripto</strong> pagás IVA, Ganancias y autónomos, pero podés descontar el IVA de tus compras y facturar a empresas que necesitan factura A. "
            "Suele convenir pasarse cuando te acercás al tope de la K, cuando tus clientes son empresas responsables inscriptas o cuando tenés muchas compras con IVA.</p>"),
    body=f"""
<h2>Comparación rápida</h2>
{table(["", "Monotributo", "Responsable inscripto"], [
        ["Impuestos", "Cuota mensual fija (impuesto + jubilación + obra social)", "IVA, Ganancias y aportes de autónomos"],
        ["Factura que emitís", "C", "A (a responsables inscriptos) o B (a consumidores finales)"],
        ["IVA de tus compras", "No se descuenta", "Se descuenta como crédito fiscal"],
        ["Límite de facturación", f"Hasta {money(K['tope'])} en 12 meses", "Sin límite"],
        ["Carga administrativa", "Baja", "Mayor: declaraciones juradas mensuales y anuales"],
        ["Atractivo para empresas clientes", "Menor (no les genera crédito de IVA)", "Mayor"],
    ])}
<h2>Cuándo conviene seguir en el monotributo</h2>
<ul><li>Facturás cómodamente por debajo de los topes.</li><li>Tus clientes son consumidores finales.</li><li>Tenés pocos gastos con IVA.</li></ul>
<h2>Cuándo conviene evaluar el pase a responsable inscripto</h2>
<ul><li>Estás cerca del tope de la K o creciendo rápido.</li><li>Tus clientes son empresas que te piden factura A.</li><li>Comprás insumos o equipos con mucho IVA.</li><li>Tenés riesgo de exclusión: mejor pasar ordenadamente que ser excluido.</li></ul>
<p class="note">La comparación correcta depende de tus números: margen, tipo de clientes, deducciones y escala de Ganancias. Un contador puede simular los dos escenarios.</p>
{cta("persona", "inscripcion", "Simulá tus dos escenarios con un contador", "Te mostramos cuánto pagarías en cada régimen con tus números reales.")}""",
    faqs=[
        ("¿Puedo pasar del monotributo a responsable inscripto cuando quiera?", "Sí, podés renunciar al monotributo y darte de alta en IVA y Ganancias. Tené en cuenta que después de renunciar no podés volver al monotributo hasta pasados 3 años calendario."),
        ("¿Un responsable inscripto paga más impuestos?", "No necesariamente. Depende del margen y de cuánto IVA podés descontar de tus compras. Con márgenes bajos y muchas compras, la diferencia puede ser menor de lo que parece."),
    ],
    sources=[ARCA_MONO, LEY_MONO, ARCA],
    related=["/monotributo/exclusion/", "/monotributo/categorias/", "/contador/cuanto-cobra-un-contador/"],
    side_cta=("persona", "inscripcion", "¿Te conviene cambiar de régimen?", "Un contador simula los dos escenarios con tus números. Gratis."),
))

# ------------------------------------------------------------------ test del contador
PAGES.append(dict(
    path="/contador/tu-contador-lo-hace-bien/", kind="article", crumbs=[CONT_CRUMB],
    title="¿Tu contador está haciendo bien las cosas? Test de 8 preguntas",
    description="Test gratuito de 8 preguntas para saber si tu contador cumple lo básico: recategorizaciones, vencimientos, Domicilio Fiscal Electrónico y comunicación.",
    h1="¿Tu contador está haciendo bien las cosas? Hacé el test",
    about=["Contador público", "Servicios contables"],
    answer=("<p>Un buen contador te avisa antes de cada recategorización, controla tus vencimientos, revisa tu Domicilio Fiscal Electrónico, te responde en un plazo razonable "
            "y te deja claro qué incluye su abono. Si fallan dos o más de estas cosas, conviene pedir una segunda opinión. El test de abajo te da un resultado en un minuto.</p>"),
    body=quiz("test-contador", "Respondé con sinceridad", [
        ("¿Te avisó antes de la última recategorización si tenías que cambiar de categoría?", 1),
        ("¿Sabés en qué categoría o régimen estás y por qué?", 1),
        ("¿Te responde las consultas en menos de 48 horas hábiles?", 1),
        ("¿Te recuerda los vencimientos o los paga en término?", 1),
        ("¿Revisa tu Domicilio Fiscal Electrónico o te enseñó a hacerlo?", 1),
        ("¿Te explicó qué deducciones o beneficios podés aprovechar?", 1),
        ("¿Tenés copia de las declaraciones juradas que presentó por vos?", 1),
        ("¿Te pasó por escrito qué incluye su abono mensual?", 1),
    ], [
        {"min": 0, "title": "Conviene una segunda opinión", "text": "Varios puntos básicos no se están cumpliendo. Puede haber riesgos (multas, recategorizaciones de oficio) o plata que estás dejando sobre la mesa."},
        {"min": 4, "title": "Hay cosas para mejorar", "text": "Lo básico está, pero hay puntos flojos. Una revisión independiente puede confirmar que todo esté en orden."},
        {"min": 7, "title": "¡Buen trabajo de tu contador!", "text": "Cumple con lo esencial. Si igual querés comparar precio o servicio, podés pedir una cotización sin compromiso."},
    ], "/diagnostico/?perfil=persona&tema=cambiar-contador", "Pedir una segunda opinión gratis") + f"""
<h2>Qué debería hacer un contador por un monotributista</h2>
<ul>
<li>Controlar tu categoría todo el año y hacer la recategorización en enero y julio.</li>
<li>Vigilar que no te acerques a una causal de exclusión.</li>
<li>Revisar el Domicilio Fiscal Electrónico y avisarte de cualquier intimación.</li>
<li>Si sos responsable inscripto: liquidar IVA, Ganancias y autónomos, y presentar las declaraciones juradas en término.</li>
<li>Explicarte en simple qué pagás y por qué.</li>
</ul>
<h2>Cómo cambiar de contador sin problemas</h2>
<p>Pedile al contador actual las constancias de lo presentado, revocá la delegación de servicios en ARCA y delegalos al nuevo profesional. Más detalle en <a href="/contador/como-cambiar-de-contador/">cómo cambiar de contador</a>.</p>""",
    faqs=[
        ("¿Cómo sé si mi contador presentó mis declaraciones juradas?", "Con tu clave fiscal podés consultar en ARCA las declaraciones presentadas y los pagos. También podés pedirle a tu contador los acuses de recibo."),
        ("¿Es normal que mi contador me pida la clave fiscal?", "Lo recomendable es delegarle los servicios que necesita desde el Administrador de Relaciones de ARCA, sin compartir tu clave."),
    ],
    sources=[ARCA],
    related=["/contador/cuanto-cobra-un-contador/", "/contador/como-cambiar-de-contador/", "/monotributo/recategorizacion/"],
    side_cta=("persona", "cambiar-contador", "¿Querés una segunda opinión?", "Un contador revisa tu situación gratis y te dice si está todo en orden."),
    schema=[{"@type": "WebApplication", "name": "Test: ¿tu contador lo hace bien?", "applicationCategory": "BusinessApplication", "operatingSystem": "Web",
             "offers": {"@type": "Offer", "price": "0", "priceCurrency": "ARS"}, "url": C.SITE_URL + "/contador/tu-contador-lo-hace-bien/"}],
))

# ------------------------------------------------------------------ cuánto cobra un contador
PAGES.append(dict(
    path="/contador/cuanto-cobra-un-contador/", kind="article", crumbs=[CONT_CRUMB, ("Cuánto cobra un contador", "/contador/cuanto-cobra-un-contador/")],
    title="¿Cuánto cobra un contador en 2026? Qué define el precio",
    description="De qué depende cuánto cobra un contador para monotributistas, responsables inscriptos y empresas, qué debería incluir el abono y cómo pedir una cotización.",
    h1="¿Cuánto cobra un contador? Qué define el precio y qué debería incluir",
    about=["Honorarios de contador", "Servicios contables"],
    answer=("<p>No hay un precio único: el honorario depende de tu régimen (monotributo, responsable inscripto o sociedad), la cantidad de comprobantes, si tenés empleados, "
            "en cuántas provincias operás y si necesitás auditoría. Un monotributista suele pagar un abono mensual bajo; una empresa en régimen general, bastante más. "
            "Lo importante es que el presupuesto detalle por escrito qué incluye. Podés pedir una cotización gratis con el diagnóstico.</p>"),
    body=f"""
<h2>Qué hace variar el precio</h2>
{table(["Factor", "Por qué impacta"], [
        ["Régimen fiscal", "Responsable inscripto o sociedad implican más declaraciones juradas que el monotributo."],
        ["Volumen de comprobantes", "Más facturas y compras requieren más registración y control."],
        ["Empleados", "La liquidación de sueldos y cargas sociales suele cotizarse aparte."],
        ["Provincias", "Operar en varias jurisdicciones suma Convenio Multilateral."],
        ["Servicios adicionales", "Auditoría, balances, trámites societarios o atención de fiscalizaciones."],
    ])}
<h2>Qué debería incluir un abono de monotributo</h2>
<ul><li>Control de categoría y recategorizaciones.</li><li>Recordatorio de vencimientos.</li><li>Revisión del Domicilio Fiscal Electrónico.</li><li>Consultas por mensaje con plazo de respuesta definido.</li></ul>
<h2>Qué debería incluir un abono de responsable inscripto</h2>
<ul><li>Liquidación mensual de IVA e Ingresos Brutos.</li><li>Declaración jurada anual de Ganancias y Bienes Personales.</li><li>Aportes de autónomos.</li><li>Atención de requerimientos simples de ARCA.</li></ul>
{cta("persona", "cambiar-contador", "Pedí una cotización sin compromiso", "Contanos tu situación y recibí una propuesta clara de un estudio aliado.", button="Cotizar mi contador")}
<h2>Cómo comparar presupuestos</h2>
<ol><li>Pedí que detallen qué incluye y qué se cobra aparte.</li><li>Preguntá por el plazo de respuesta y el canal (mail, WhatsApp).</li><li>Confirmá quién es el contador matriculado responsable.</li><li>Preguntá cómo va a acceder a ARCA (delegación de servicios o clave) y cómo protege ese acceso.</li></ol>""",
    faqs=[
        ("¿Conviene un contador online o un estudio tradicional?", "Depende del caso. Para un monotributista, un servicio online suele ser práctico y económico. Para una empresa con varias provincias o necesidad de auditoría, conviene un estudio con equipo especializado."),
        ("¿Qué datos necesito para pedir una cotización?", "Tu régimen, actividad, facturación aproximada, cantidad de comprobantes por mes, si tenés empleados y en qué provincias operás."),
    ],
    sources=[ARCA],
    related=["/contador/tu-contador-lo-hace-bien/", "/contador/como-cambiar-de-contador/", "/empresas/como-elegir-estudio-contable/"],
    side_cta=("persona", "cambiar-contador", "Cotizá tu contador en 1 minuto", "Te conectamos con un estudio aliado que te pasa una propuesta clara."),
))

# ------------------------------------------------------------------ cambiar de contador
PAGES.append(dict(
    path="/contador/como-cambiar-de-contador/", kind="article", crumbs=[CONT_CRUMB, ("Cómo cambiar de contador", "/contador/como-cambiar-de-contador/")],
    title="Cómo cambiar de contador sin perder información",
    description="Paso a paso para cambiar de contador: qué documentación pedir, cómo revocar y delegar servicios en ARCA y qué revisar en el traspaso.",
    h1="Cómo cambiar de contador sin perder información (paso a paso)",
    about=["Cambio de contador", "Delegación de servicios ARCA"],
    answer=("<p>Para cambiar de contador: pedí al actual las declaraciones juradas, papeles de trabajo y constancias de pago; revocá su acceso en el Administrador de Relaciones de ARCA; "
            "delegá los servicios al nuevo profesional (sin darle tu clave fiscal) y pedile una revisión inicial de tu situación. Hacelo lejos de un vencimiento importante.</p>"),
    body=f"""
<h2>Paso a paso</h2>
<ol>
<li><strong>Elegí el momento:</strong> evitá cambiar justo antes de una recategorización o de una declaración jurada anual.</li>
<li><strong>Pedí la documentación:</strong> declaraciones juradas presentadas, acuses, papeles de trabajo, libros y constancias de pago.</li>
<li><strong>Revisá accesos:</strong> en el Administrador de Relaciones de Clave Fiscal, revocá los servicios delegados al contador anterior.</li>
<li><strong>Delegá al nuevo:</strong> asigná solo los servicios que necesita. No compartas tu clave fiscal.</li>
<li><strong>Pedí un diagnóstico inicial:</strong> deudas, presentaciones pendientes, categoría correcta e intimaciones en el Domicilio Fiscal Electrónico.</li>
</ol>
{cta("persona", "cambiar-contador", "¿Buscás un contador nuevo?", "Te conectamos con un estudio aliado que hace el traspaso y una revisión inicial.")}
<h2>Qué revisar en el traspaso</h2>
<ul><li>Que no haya declaraciones juradas sin presentar.</li><li>Planes de pago vigentes y su estado.</li><li>Notificaciones en el Domicilio Fiscal Electrónico.</li><li>Categoría de monotributo o inscripciones en IVA, Ganancias e Ingresos Brutos.</li></ul>""",
    faqs=[("¿Necesito avisarle a ARCA que cambié de contador?", "No hay un aviso formal: alcanza con revocar las delegaciones al contador anterior y delegar los servicios al nuevo desde el Administrador de Relaciones.")],
    sources=[ARCA],
    related=["/contador/tu-contador-lo-hace-bien/", "/contador/cuanto-cobra-un-contador/"],
    side_cta=("persona", "cambiar-contador", "¿Buscás contador?", "Te conectamos con un estudio aliado. Gratis y sin compromiso."),
))
