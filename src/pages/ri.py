"""Responsables inscriptos e IVA."""
from lib import cta, table, ARCA
import config as C

RI = ("Responsables inscriptos", "/responsables-inscriptos/")
MISCOMP = ("ARCA — Mis Comprobantes", "https://www.arca.gob.ar/miscomprobantes/")
IVA_ARCA = ("ARCA — IVA", "https://www.arca.gob.ar/iva/")
PAGES = []

AUTORIZACION = (f"Autorizo a {C.TITULAR} a usar el usuario y la clave fiscal que ingreso, en mi nombre, solo para consultar en ARCA el servicio "
                "Mis Comprobantes (emitidos y recibidos) del CUIT indicado y calcular mi posición de IVA. No se usarán para ninguna otra operación. "
                "La clave viaja cifrada, se guarda cifrada solo si marco la opción de guardar acceso y es procesada por un proveedor tecnológico que ejecuta la consulta. "
                "Puedo revocar esta autorización cuando quiera borrando mi cuenta o cambiando mi clave fiscal. Declaro ser titular del CUIT o estar autorizado por su titular.")

CONECTAR = f"""<div class="tool" id="iva-auto">
<h2 style="margin:0 0 4px;font-size:24px">¿Cuánto IVA vas a pagar este mes?</h2>
<p style="margin:0 0 4px;color:var(--muted)">Conectá tu CUIT una sola vez. Nuestro robot entra a ARCA, revisa tus comprobantes emitidos y recibidos y te dice cuánto viene. Sin subir archivos y sin llamar a tu contador.</p>
<p id="iva-ya-conectado" class="note" hidden style="margin-top:12px">Ya conectaste tu CUIT en este navegador. <a href="/iva/mi-cuenta/">Ir a mi panel de IVA →</a></p>
<form id="iva-conectar" novalidate autocomplete="off">
<div class="row2">
<div><label for="i-cuit">CUIT a consultar</label><input id="i-cuit" name="cuit" type="text" inputmode="numeric" placeholder="30-12345678-9" required></div>
<div><label for="i-usuario">Usuario de ARCA (CUIT/CUIL con el que ingresás)</label><input id="i-usuario" name="usuario" type="text" inputmode="numeric" placeholder="Si es el mismo, dejalo vacío"></div>
</div>
<label for="i-clave">Clave fiscal</label><input id="i-clave" name="clave" type="password" autocomplete="off" required maxlength="64">
<p class="src" style="margin:6px 0 0">Si consultás una sociedad, usá el CUIT de la empresa arriba y tu CUIL como usuario (el del representante con acceso a Mis Comprobantes).</p>
<div class="row2">
<div><label for="i-nombre">Nombre y apellido</label><input id="i-nombre" name="nombre" type="text" autocomplete="name" required></div>
<div><label for="i-email">Email</label><input id="i-email" name="email" type="email" autocomplete="email" required></div>
</div>
<label for="i-wa">WhatsApp (opcional, para avisos de vencimiento)</label><input id="i-wa" name="whatsapp" type="tel" autocomplete="tel">
<div class="hp" aria-hidden="true"><label>No completar<input type="text" name="web" tabindex="-1" autocomplete="off"></label></div>
<label class="chk"><input type="checkbox" name="guardar" checked><span><strong>Guardar mi acceso cifrado</strong> para consultar cuando quiera desde mi panel, sin volver a ingresar la clave.</span></label>
<label class="chk"><input type="checkbox" name="autorizacion" required><span id="txt-autorizacion">{AUTORIZACION}</span></label>
<button class="btn" type="submit" style="width:100%">Consultar mi IVA</button>
<p class="err" role="alert"></p>
<p class="src">🔒 Conexión cifrada · clave guardada con AES-256 · podés borrar tu cuenta en un clic · <a href="/iva/seguridad/">cómo protegemos tu acceso</a></p>
</form>
<div id="iva-progreso" hidden>
<div id="iva-espera" class="result"><p style="margin:0"><strong>Consultando ARCA…</strong> <span id="iva-seg">0</span> s. Suele tardar menos de un minuto.</p></div>
<div id="iva-resultado" class="result"></div>
<div id="iva-post" hidden class="tool" style="margin-top:16px"><h3 style="margin:0 0 6px;font-size:18px">Tu enlace privado</h3>
<p style="margin:0 0 8px;font-size:15px">Con este enlace volvés a tu panel y consultás cuando quieras. Guardalo como si fuera una contraseña: no lo compartas.</p>
<input id="iva-link" type="text" readonly><button type="button" class="btn sec sm" id="iva-copiar" style="margin-top:10px">Copiar enlace</button>
<a class="btn sm" href="/iva/mi-cuenta/" style="margin-top:10px">Ir a mi panel</a></div>
</div>
</div>"""

TOOL = """<details class="tool" id="iva-tool"><summary style="cursor:pointer;font-weight:700;font-size:18px">¿Preferís no conectar tu clave? Subí tus archivos o cargá los montos a mano</summary>
<p style="margin:10px 0 8px;color:var(--muted)"><strong>Los archivos se procesan en tu navegador: no se envían a ningún servidor.</strong></p>
<h3 style="font-size:17px;margin:18px 0 4px">1. Desde Mis Comprobantes de ARCA</h3>
<p class="src" style="margin:0">Descargá los <strong>Emitidos</strong> y los <strong>Recibidos</strong> del mes en CSV o Excel (Mis Comprobantes → Buscar → Exportar).</p>
<div class="row2">
<div><label for="f-emitidos">Comprobantes emitidos (ventas)</label><input id="f-emitidos" type="file" accept=".csv,.xlsx,.xls,text/csv"><div class="src" id="st-emitidos" aria-live="polite"></div></div>
<div><label for="f-recibidos">Comprobantes recibidos (compras)</label><input id="f-recibidos" type="file" accept=".csv,.xlsx,.xls,text/csv"><div class="src" id="st-recibidos" aria-live="polite"></div></div>
</div>
<div id="iva-mes-wrap" hidden><label for="iva-mes">Mes a calcular</label><select id="iva-mes"></select><p class="src" id="iva-file-info" style="margin:6px 0 0"></p></div>
<h3 style="font-size:17px;margin:22px 0 4px">2. Montos del mes</h3>
<div class="row2">
<div><label for="iva-deb">Débito fiscal (IVA de tus ventas)</label><input id="iva-deb" type="text" inputmode="numeric" placeholder="Ej.: 2.100.000"></div>
<div><label for="iva-cred">Crédito fiscal (IVA de tus compras)</label><input id="iva-cred" type="text" inputmode="numeric" placeholder="Ej.: 1.300.000"></div>
<div><label for="iva-ret">Retenciones y percepciones de IVA sufridas</label><input id="iva-ret" type="text" inputmode="numeric" placeholder="Ej.: 150.000"></div>
<div><label for="iva-sta">Saldo técnico a favor del mes anterior</label><input id="iva-sta" type="text" inputmode="numeric" placeholder="0"></div>
<div><label for="iva-sld">Saldo de libre disponibilidad anterior</label><input id="iva-sld" type="text" inputmode="numeric" placeholder="0"></div>
</div>
<div class="result" id="iva-out" hidden aria-live="polite"></div>
<noscript><p>Esta calculadora necesita JavaScript.</p></noscript>
</details>"""

PAGES.append(dict(
    path="/iva/", kind="article", crumbs=[RI, ("Calculadora de IVA", "/iva/")], scripts=["iva.js", "iva-cuenta.js"],
    title="IVA del mes: sabé cuánto vas a pagar, automático",
    description="Conectá tu CUIT y nuestro robot consulta ARCA y te dice cuánto IVA viene este mes, con tiempo para planificar compras. Sin subir archivos ni llamar al contador.",
    h1="Calculadora de IVA del mes: cuánto vas a pagar y cómo planificarlo",
    about=["IVA", "Débito fiscal", "Crédito fiscal", "Responsable inscripto"],
    answer=("<p>El IVA del mes es el <strong>débito fiscal</strong> (IVA de tus ventas) menos el <strong>crédito fiscal</strong> (IVA de tus compras con factura A) y el saldo técnico del mes anterior. "
            "Al resultado le restás las <strong>retenciones y percepciones</strong> de IVA y el saldo de libre disponibilidad. Si al día 20 ya sabés cuánto viene, todavía estás a tiempo "
            "de adelantar compras necesarias, pedir notas de crédito pendientes o preparar la caja. Conectá tu CUIT y nuestro robot lo calcula con tus comprobantes de ARCA.</p>"),
    body=CONECTAR + TOOL + f"""
<h2>Cómo se calcula el IVA a pagar</h2>
{table(["Paso", "Cálculo"], [
        ["1. Débito fiscal", "IVA facturado en tus ventas del mes (menos notas de crédito emitidas)"],
        ["2. Crédito fiscal", "IVA de tus compras con factura A del mes (menos notas de crédito recibidas)"],
        ["3. Impuesto determinado", "Débito − crédito − saldo técnico del mes anterior. Si da negativo, es saldo técnico a favor"],
        ["4. Saldo a pagar", "Impuesto determinado − retenciones y percepciones − saldo de libre disponibilidad"],
    ])}
<h2>Ejemplo</h2>
<p>Vendiste $10.000.000 + IVA (débito $2.100.000) y compraste $6.000.000 + IVA (crédito $1.260.000). Te retuvieron $150.000 de IVA. El impuesto determinado es $840.000 y el saldo a pagar, <strong>$690.000</strong>. Si tenías previsto comprar insumos por $3.300.000 + IVA el mes que viene, adelantarlos a este mes genera $693.000 de crédito y el saldo a pagar queda en cero.</p>
<p class="note">Adelantar compras no ahorra impuesto: adelanta el crédito fiscal y usa caja. Tiene sentido cuando la compra es necesaria igual (stock, insumos, equipos) y cuando la factura sale a tu nombre con fecha del mes.</p>
{cta("ri", "iva-planificacion", "Planificá el IVA todos los meses", "Un especialista revisa tu posición de IVA antes del vencimiento y te dice qué conviene hacer.", button="Quiero planificar mi IVA")}
<h2>5 formas de planificar mejor el IVA</h2>
<ol>
<li><strong>Mirá el IVA antes del día 20</strong>, no cuando llega el vencimiento.</li>
<li><strong>Pedí a tiempo las facturas y notas de crédito</strong> de tus proveedores: si llegan el mes siguiente, el crédito se corre.</li>
<li><strong>Coordiná las compras grandes</strong> (stock, bienes de uso) con tu posición de IVA.</li>
<li><strong>Controlá las retenciones y percepciones:</strong> si generan saldo a favor todos los meses, se puede pedir la exclusión o reducción.</li>
<li><strong>Revisá que todo el crédito sea computable:</strong> facturas A a tu CUIT, vinculadas a la actividad, y proveedores sin observaciones.</li>
</ol>
<h2>Sin conectar tu clave: cómo descargar tus comprobantes</h2>
<ol><li>Entrá con tu clave fiscal al servicio <strong>Mis Comprobantes</strong>.</li><li>Elegí <strong>Emitidos</strong>, filtrá las fechas del mes y tocá <strong>Buscar</strong>.</li><li>Exportá en CSV o Excel y repetí con <strong>Recibidos</strong>.</li><li>Subí los dos archivos en la calculadora manual. No se envían a ningún servidor.</li></ol>
""",
    faqs=[
        ("¿Cuándo vence el IVA?", "El IVA es mensual y vence en la segunda quincena del mes siguiente, según la terminación de tu CUIT. Confirmá la fecha exacta en el calendario de vencimientos de ARCA."),
        ("¿Las facturas B y C generan crédito fiscal?", "No. Solo las facturas A (y M, con sus particularidades) discriminan IVA que podés computar como crédito fiscal."),
        ("¿Qué es el saldo técnico de IVA?", "Es el crédito fiscal que excede al débito en un mes. No se devuelve en general: se traslada y se usa en los meses siguientes."),
        ("¿Qué es el saldo de libre disponibilidad?", "Es el saldo a favor que se origina en retenciones, percepciones o pagos a cuenta de IVA. A diferencia del saldo técnico, en ciertos casos se puede compensar con otros impuestos o pedir en devolución."),
        ("¿Es seguro conectar mi clave fiscal?", "La clave viaja cifrada, se guarda cifrada con AES-256 solo si lo autorizás y se usa únicamente para consultar Mis Comprobantes. Podés borrar tu cuenta en un clic y, para mayor tranquilidad, cambiar tu clave fiscal cuando quieras. Ver <a href=\"/iva/seguridad/\">cómo protegemos tu acceso</a>."),
        ("¿Puedo usarlo sin dar mi clave?", "Sí: descargá tus comprobantes de Mis Comprobantes y subilos en la calculadora manual. Esos archivos se procesan en tu navegador y no se envían a ningún servidor."),
    ],
    sources=[MISCOMP, IVA_ARCA, ("ARCA — Calendario de vencimientos", "https://www.arca.gob.ar/vencimientos/")],
    related=["/responsables-inscriptos/", "/empresas/saldos-a-favor/", "/calendario-fiscal/"],
    side_cta=("ri", "iva-planificacion", "¿El IVA te llega siempre de sorpresa?", "Un especialista revisa tu posición antes de cada vencimiento. Primera consulta sin costo."),
    schema=[{"@type": "WebApplication", "name": "Calculadora de IVA del mes", "applicationCategory": "FinanceApplication", "operatingSystem": "Web",
             "offers": {"@type": "Offer", "price": "0", "priceCurrency": "ARS"}, "url": C.SITE_URL + "/iva/",
             "featureList": ["Consulta automática de Mis Comprobantes en ARCA", "Importa comprobantes emitidos y recibidos de Mis Comprobantes (CSV o Excel)", "Calcula débito, crédito, saldo técnico y saldo a pagar", "Estima compras necesarias para compensar"]}],
))

PAGES.append(dict(
    path="/responsables-inscriptos/", kind="article", crumbs=[RI],
    title="Responsable inscripto: qué impuestos pagás y cómo planificarlos",
    description="Guía para responsables inscriptos: IVA, Ganancias, autónomos e Ingresos Brutos, obligaciones de cada mes y cómo planificar para pagar lo justo.",
    h1="Responsable inscripto: qué impuestos pagás y cómo planificarlos",
    about=["Responsable inscripto", "IVA", "Impuesto a las Ganancias", "Ingresos Brutos"],
    answer=("<p>Como responsable inscripto pagás <strong>IVA</strong> todos los meses, <strong>Ganancias</strong> con una declaración anual y anticipos, <strong>aportes de autónomos</strong> "
            "(si sos persona humana) e <strong>Ingresos Brutos</strong> en tu provincia. La diferencia con el monotributo es que cada impuesto depende de tus números reales, así que "
            "<strong>planificar</strong> (cuándo comprar, qué deducir, cuánto anticipar) cambia cuánto pagás y cuándo.</p>"),
    body=f"""
<h2>Tus obligaciones, mes a mes</h2>
{table(["Impuesto", "Frecuencia", "Qué planificar"], [
        ["IVA", "Mensual", "Calcular antes del día 20, coordinar compras, controlar retenciones"],
        ["Ingresos Brutos", "Mensual (anual en algunos regímenes)", "Alícuotas de padrón, retenciones bancarias, Convenio Multilateral"],
        ["Ganancias", "Anual + anticipos", "Deducciones, gastos computables, reducción de anticipos si bajó la actividad"],
        ["Autónomos", "Mensual", "Categoría correcta según la actividad"],
        ["Bienes Personales", "Anual + anticipos", "Valuación de bienes y exenciones"],
    ])}
<h2>Herramientas para responsables inscriptos</h2>
<div class="grid">
<a class="card" href="/iva/"><h3>Calculadora de IVA del mes</h3><p>Subí tus comprobantes y sabé cuánto viene antes del vencimiento.</p><span class="go">Calcular →</span></a>
<a class="card" href="/empresas/saldos-a-favor/"><h3>Estimador de saldos a favor</h3><p>Cuánto capital te inmovilizan las retenciones y percepciones.</p><span class="go">Estimar →</span></a>
<a class="card" href="/empresas/fiscalizacion-arca/"><h3>Riesgo ante ARCA</h3><p>Checklist de 8 controles clave.</p><span class="go">Revisar →</span></a>
</div>
<h2>Dónde suele perder plata un responsable inscripto</h2>
<ul>
<li>Facturas de compra que llegan tarde y corren el crédito fiscal al mes siguiente.</li>
<li>Retenciones y percepciones que generan saldos a favor que nadie reclama.</li>
<li>Anticipos de Ganancias calculados sobre un año mejor que el actual.</li>
<li>Gastos deducibles que no se computan por falta de comprobante.</li>
<li>Alícuotas de Ingresos Brutos mal asignadas en el padrón provincial.</li>
</ul>
{cta("ri", None, "¿Qué no te está diciendo tu contador?", "Una segunda opinión independiente revisa tu IVA, Ganancias e Ingresos Brutos y te muestra dónde podés pagar lo justo.", button="Quiero una segunda opinión")}
<h2>¿Venís del monotributo?</h2>
<p>Si te excluyeron o pasaste voluntariamente, mirá <a href="/monotributo/monotributo-o-responsable-inscripto/">qué cambia al pasar a responsable inscripto</a>: vas a emitir factura A o B, presentar IVA todos los meses y llevar registros de compras.</p>""",
    faqs=[
        ("¿Qué factura emite un responsable inscripto?", "Factura A a otros responsables inscriptos y factura B a consumidores finales, monotributistas y exentos."),
        ("¿Puedo reducir los anticipos de Ganancias?", "Sí, si estimás que el impuesto del año va a ser menor que el que se usó de base para los anticipos, se puede solicitar la reducción en ARCA. Conviene hacerlo con fundamento, porque si el impuesto final resulta mayor se generan intereses."),
    ],
    sources=[IVA_ARCA, ARCA],
    related=["/iva/", "/empresas/saldos-a-favor/", "/monotributo/monotributo-o-responsable-inscripto/"],
    side_cta=("ri", None, "Segunda opinión para responsables inscriptos", "Revisamos tu IVA, Ganancias e Ingresos Brutos. Primera consulta sin costo."),
))

PAGES.append(dict(
    path="/iva/mi-cuenta/", kind="custom", noindex=True, crumbs=[RI, ("Calculadora de IVA", "/iva/"), ("Mi panel", "/iva/mi-cuenta/")], scripts=["iva-cuenta.js"],
    title="Mi panel de IVA", description="Panel privado de IVA.", h1="Mi panel de IVA",
    body="""<div class="wrap" style="max-width:860px;padding:20px 20px 80px">
<h1>Mi panel de IVA</h1>
<p id="p-msg" aria-live="polite" class="src"></p>
<div id="iva-panel" hidden>
<div class="tool" style="margin-top:0"><p style="margin:0">CUIT <strong id="p-cuit"></strong> · <span id="p-guardado" class="src"></span></p>
<div id="p-reconectar" hidden><div class="row2"><div><label for="p-usuario">Usuario de ARCA (si es distinto del CUIT)</label><input id="p-usuario" type="text" inputmode="numeric"></div>
<div><label for="p-clave">Clave fiscal</label><input id="p-clave" type="password" autocomplete="off" maxlength="64"></div></div>
<label class="chk"><input type="checkbox" id="p-guardar"><span>Guardar mi acceso cifrado para la próxima vez</span></label></div>
<div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:14px"><button type="button" class="btn" id="p-actual">Consultar el mes en curso</button><button type="button" class="btn sec" id="p-anterior">Consultar el mes anterior</button></div></div>
<div id="p-resultado" class="result"></div>
<h2 style="font-size:21px">Historial</h2><div id="p-hist"><p class="src">Todavía no hay consultas anteriores.</p></div>
<h2 style="font-size:21px">Tu acceso</h2>
<p>Podés borrar tu cuenta cuando quieras: eliminamos tu acceso cifrado, tus consultas y tus datos. <button type="button" class="btn sec sm" id="p-borrar">Borrar mi acceso y mis datos</button></p>
</div></div>""",
))

PAGES.append(dict(
    path="/iva/seguridad/", kind="page", crumbs=[RI, ("Calculadora de IVA", "/iva/"), ("Seguridad", "/iva/seguridad/")],
    title="Cómo protegemos tu clave fiscal", description="Cómo ciframos, usamos y borramos tu acceso a ARCA en el servicio de IVA automático.",
    h1="Cómo protegemos tu clave fiscal",
    body="""<p>Para decirte cuánto IVA viene sin que tengas que hacer nada, nuestro robot necesita entrar a ARCA en tu nombre. Así protegemos ese acceso:</p>
<h2>Qué usamos y para qué</h2><ul><li>Tu usuario y clave fiscal se usan <strong>solo</strong> para consultar el servicio Mis Comprobantes (emitidos y recibidos) del CUIT que indicaste.</li><li>No presentamos declaraciones, no emitimos comprobantes, no pagamos ni modificamos nada en ARCA.</li></ul>
<h2>Cómo la guardamos</h2><ul><li>La clave viaja por una conexión cifrada (HTTPS).</li><li>Si elegís guardar tu acceso, se almacena cifrada con <strong>AES-256-GCM</strong>. La llave de cifrado está separada de la base de datos y nadie del equipo ve tu clave en texto plano.</li><li>Si no elegís guardarla, se usa para la consulta y se descarta.</li><li>Tu enlace privado no se guarda: guardamos solo una huella (hash) para reconocerlo.</li><li>De tus comprobantes guardamos solo los totales del mes, no el detalle.</li></ul>
<h2>Quién la procesa</h2><p>La consulta la ejecuta un proveedor tecnológico especializado en automatizaciones de ARCA, que recibe la clave solo para esa consulta.</p>
<h2>Cómo revocar el acceso</h2><ul><li>Desde tu panel: “Borrar mi acceso y mis datos”. Se elimina todo en el momento.</li><li>Cambiando tu clave fiscal en ARCA: el acceso guardado deja de funcionar.</li></ul>
<h2>Alternativa sin clave</h2><p>Si preferís no conectar tu clave, usá la <a href="/iva/">calculadora manual</a>: subís los archivos de Mis Comprobantes y se procesan en tu navegador.</p>""",
))
