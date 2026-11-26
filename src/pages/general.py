"""Home, embudo, herramientas, referencia y páginas institucionales."""
from lib import MONO, money, cta, diag_widget, table, aliados_txt, esc, ARCA, ARCA_MONO, COMARB, AAIP, BO
import config as C

A, K = MONO["categorias"][0], MONO["categorias"][-1]
RECAT = MONO["proxima_recategorizacion"]
PAGES = []

HOME_FAQS = [
    ("¿El diagnóstico tiene costo?", "No. El diagnóstico es gratis y sin compromiso. Si después querés contratar al estudio, te pasan su propuesta de honorarios antes de empezar."),
    ("¿Qué es una segunda opinión impositiva?", "Es una revisión independiente de cómo se están llevando tus impuestos: categoría o régimen, saldos a favor, alícuotas, beneficios no aprovechados y riesgos. No reemplaza a tu contador; le suma una mirada externa."),
    ("¿Me van a pedir la clave fiscal?", "Para el diagnóstico, no. Solo el servicio de <a href=\"/iva/\">IVA automático</a> la usa, con tu autorización expresa, cifrada y únicamente para consultar Mis Comprobantes. Ver <a href=\"/iva/seguridad/\">cómo la protegemos</a>."),
    ("¿A quién le llegan mis datos?", f"Solo al estudio contable aliado más adecuado para tu caso ({aliados_txt()}), y solo si das tu consentimiento en el formulario."),
    ("¿Ustedes son un estudio contable?", f"No. {C.SITE_NAME} es un sitio informativo que te conecta con estudios aliados. El asesoramiento lo da siempre un contador matriculado del estudio."),
]


def faq_html(faqs):
    return '<div class="faq">' + "".join(f'<details><summary>{q}</summary><p>{a}</p></details>' for q, a in faqs) + '</div>'


HOME = f"""
<section class="hero"><div class="wrap">
<div class="hero-txt">
<span class="pill">Segunda opinión gratis · 2 minutos</span>
<h1>Tus impuestos bien llevados te hacen ganar plata</h1>
<p class="lead">¿Querés saber qué no te está diciendo tu contador o tu departamento de impuestos? Un especialista revisa tu caso y te muestra dónde pagás de más, qué podés recuperar y cómo planificar.</p>
<ul class="checks">
<li>Para empresas, responsables inscriptos y profesionales</li>
<li>Te atiende un contador matriculado de un estudio aliado</li>
<li>El diagnóstico no te pide la clave fiscal</li>
<li>Recibís la propuesta antes de decidir nada</li>
</ul>
</div>
<div style="flex:1 1 420px;min-width:0">{diag_widget()}</div>
</div></section>

<!-- SECCION AGENTICA: PRIMER ESTUDIO CONTABLE AGENTICO -->
<section class="wrap" style="padding-top:56px;padding-bottom:20px">
<div style="text-align:center;max-width:920px;margin:0 auto 36px">
<div style="display:inline-flex;align-items:center;gap:8px;background:#EBF5FF;color:#0052CC;padding:6px 16px;border-radius:999px;font-size:14px;font-weight:700;margin-bottom:14px;border:1px solid #B3D4FF">
⚡ El Primer Estudio Contable Agéntico de Argentina
</div>
<h2 style="margin:4px 0 16px;font-size:clamp(28px,4.5vw,42px);letter-spacing:-.02em;line-height:1.15">
Dejamos obsoletos a los estudios contables tradicionales y a las apps cerradas del mercado
</h2>
<p style="color:var(--muted);font-size:19px;margin:0 auto 22px;max-width:820px;line-height:1.5">
Sin horarios de oficina de 9 a 18 hs. Sin tener que aprender otra app gris ni esperar días por un VEP. Conectá tu propia IA (Claude, ChatGPT o WhatsApp) para que audite tus cuentas, ejecute más de <strong>80 trámites oficiales en ARCA en 15 segundos</strong> y te dé análisis claros, visuales y accionables sin jerga contable.
</p>
<div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap">
<a class="btn" href="/mcp">Conectar con Claude / ChatGPT →</a>
<a class="btn sec" href="/estudios/">Modo Estudio Contable (B2B)</a>
<a class="btn sec" href="/whatsapp/">Conectar mi WhatsApp</a>
</div>
</div>

<!-- DEMO INTERACTIVA CON SELECTOR DE 4 ESCENARIOS + ANIMACIÓN REAL ESTILO CLAUDE -->
<div style="background:#FAF9F5;border-radius:20px;box-shadow:0 20px 50px -15px rgba(15,27,45,0.14);overflow:hidden;border:1px solid #E3E1D8;margin-bottom:44px">

  <!-- Barra superior estilo Claude Desktop / Claude.ai -->
  <div style="background:#F0EFEA;padding:14px 22px;display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;border-bottom:1px solid #E2E0D8;gap:12px">
    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
      <span style="width:26px;height:26px;border-radius:7px;background:#D97757;color:#fff;display:inline-flex;align-items:center;justify-content:center;font-weight:800;font-size:14px">✦</span>
      <span style="color:#1F1E1D;font-weight:700;font-size:14.5px">Claude</span>
      <span id="cd-title" style="color:#5A5852;font-size:13px;font-weight:500">Impuestos · Innovatech Solutions S.R.L.</span>
    </div>
    <span style="color:#4B4A45;font-size:12px;background:#fff;border:1px solid #DFDDD5;padding:4px 11px;border-radius:99px;display:inline-flex;align-items:center;gap:6px"><span class="c-dot-live"></span><strong>impuesto-arca-mcp</strong> · 43 tools</span>
  </div>

  <!-- Selector de Escenarios Reales (dispara animación en vivo) -->
  <div style="background:#F5F4EF;padding:12px 22px;border-bottom:1px solid #E5E3DB;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px">
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
      <span style="font-size:12px;font-weight:700;color:#6E6C66;text-transform:uppercase;letter-spacing:.05em;margin-right:4px">Elegí un ejemplo:</span>
      <button type="button" class="c-scen-btn active" data-scen="pyme" onclick="runClaudeScenario('pyme')">🧾 Factura A + Banco</button>
      <button type="button" class="c-scen-btn" data-scen="mono" onclick="runClaudeScenario('mono')">👤 Monotributo + CCMA</button>
      <button type="button" class="c-scen-btn" data-scen="estudio" onclick="runClaudeScenario('estudio')">🏢 Estudio Contable (Socio)</button>
      <button type="button" class="c-scen-btn" data-scen="defensa" onclick="runClaudeScenario('defensa')">🏛️ Tasa Municipal / SIRCREB</button>
    </div>
    <button type="button" onclick="var a=document.querySelector('.c-scen-btn.active');runClaudeScenario(a?a.getAttribute('data-scen'):'pyme')" style="background:transparent;border:0;color:#0B6E4F;font-size:12.5px;font-weight:650;cursor:pointer;font-family:inherit">↻ Reproducir</button>
  </div>

  <!-- Área de Chat Animada estilo Claude -->
  <div style="padding:26px 30px;min-height:360px;color:#1F1E1D;font-family:var(--font);font-size:14.5px;line-height:1.55">
    <div id="cd-user-box" style="display:flex;justify-content:flex-end;margin-bottom:18px;transition:opacity .25s">
      <div style="background:#EFECE6;border:1px solid #E2DFD7;padding:13px 18px;border-radius:16px 16px 4px 16px;color:#1F1E1D;max-width:84%;font-size:14.5px">
        <div id="cd-user-txt"></div>
        <div id="cd-user-att" style="display:none;align-items:center;gap:6px;margin-top:8px;background:#fff;border:1px solid #DCD9D0;border-radius:8px;padding:3px 10px;font-size:12px;color:#4A4843;font-weight:500"></div>
      </div>
    </div>

    <div id="cd-claude-row" style="display:none;gap:14px;align-items:flex-start">
      <div style="width:30px;height:30px;border-radius:50%;background:#D97757;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:14px;flex-shrink:0;margin-top:2px">✦</div>
      <div style="flex:1;min-width:0">
        <div id="cd-tools" style="display:grid;gap:6px;margin-bottom:14px"></div>
        <div id="cd-answer" style="display:none;background:#fff;border:1px solid #E4E2DA;border-radius:14px;padding:18px 20px;box-shadow:0 4px 16px rgba(0,0,0,0.03)"></div>
      </div>
    </div>
  </div>

  <!-- VIDEO DEMO REAL INTEGRADO (MP4 H.264 REPRODUCIBLE) -->
  <div style="background:#F0EFEA;border-top:1px solid #E2E0D8;padding:24px 30px">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:14px">
      <div>
        <span style="color:#0B6E4F;font-size:12px;font-weight:800;letter-spacing:.06em;text-transform:uppercase">Video real en acción · Claude + ARCA MCP</span>
        <h3 style="margin:3px 0 0;font-size:18px;color:#1F1E1D">Mirá exactamente qué pasa cuando le escribís a Claude conectado a ARCA</h3>
      </div>
      <a class="btn sm" href="/estudios/" style="background:#1F1E1D;color:#fff;border:0">¿Tenés un Estudio Contable? Ver Modo B2B →</a>
    </div>
    <div style="border-radius:12px;overflow:hidden;border:1px solid #D8D6CE;box-shadow:0 8px 24px rgba(0,0,0,0.08);background:#FAF9F5">
      <video controls autoplay muted loop playsinline poster="/assets/demo-claude-poster.png" style="width:100%;display:block;max-height:540px">
        <source src="/assets/demo-claude-arca.mp4" type="video/mp4">
        Tu navegador no soporta video HTML5.
      </video>
    </div>
  </div>
</div>
<script src="/assets/claude-demo.js" defer></script>

<!-- MATRIZ DE CAPACIDADES BOTS: EMPRESAS VS MONOTRIBUTISTAS -->
<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:24px">
  <div class="card" style="border-top:4px solid #0B6E4F">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
      <span style="font-size:24px">🏢</span>
      <h3 style="margin:0">Para Empresas y Resp. Inscriptos</h3>
    </div>
    <p style="color:var(--muted);font-size:14.5px">Automatización de obligaciones fiscales mensuales con trazabilidad técnica y seguridad jurídica.</p>
    <ul style="list-style:none;padding:0;margin:12px 0;display:grid;gap:10px;font-size:15px">
      <li style="display:flex;align-items:flex-start;gap:8px">
        <span style="color:#0B6E4F;font-weight:bold">✓</span>
        <div><strong>Facturación Electrónica A y B:</strong> Emisión en RCEL con CAE oficial, cálculo de alícuotas (21%, 10.5%, 27%) y QR.</div>
      </li>
      <li style="display:flex;align-items:flex-start;gap:8px">
        <span style="color:#0B6E4F;font-weight:bold">✓</span>
        <div><strong>Presentación DDJJ IVA (F. 2002):</strong> Liquidación preliminar con saldos técnicos a favor y acuse de recibo.</div>
      </li>
      <li style="display:flex;align-items:flex-start;gap:8px">
        <span style="color:#0B6E4F;font-weight:bold">✓</span>
        <div><strong>Cierre Libro de IVA Digital (RG 4597):</strong> Cruce automático de ventas y compras sin pasar archivos manuales.</div>
      </li>
      <li style="display:flex;align-items:flex-start;gap:8px">
        <span style="color:#0B6E4F;font-weight:bold">✓</span>
        <div><strong>Certificado de No Retención (RG 2226):</strong> Trámite para frenar retenciones cuando tenés saldo a favor acumulado.</div>
      </li>
      <li style="display:flex;align-items:flex-start;gap:8px">
        <span style="color:#0B6E4F;font-weight:bold">✓</span>
        <div><strong>ABM Puntos de Venta y CBU:</strong> Habilitación de puntos electrónicos y declaración de cuentas bancarias.</div>
      </li>
    </ul>
    <a class="btn sm" href="/mcp" style="margin-top:auto">Conectar Empresa con MCP →</a>
  </div>

  <div class="card" style="border-top:4px solid #0052CC">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
      <span style="font-size:24px">👤</span>
      <h3 style="margin:0">Para Monotributistas y Profesionales</h3>
    </div>
    <p style="color:var(--muted);font-size:14.5px">Protegé tu régimen simplificado, controlá tus límites y no pagues multas por descuidos de fecha.</p>
    <ul style="list-style:none;padding:0;margin:12px 0;display:grid;gap:10px;font-size:15px">
      <li style="display:flex;align-items:flex-start;gap:8px">
        <span style="color:#0052CC;font-weight:bold">✓</span>
        <div><strong>Recategorización Semestral Asistida:</strong> Proyección de escala en Enero y Julio con trámite guiado en ARCA.</div>
      </li>
      <li style="display:flex;align-items:flex-start;gap:8px">
        <span style="color:#0052CC;font-weight:bold">✓</span>
        <div><strong>Alerta Temprana de Topes:</strong> Semáforo en tiempo real de facturación acumulada para evitar exclusiones de oficio.</div>
      </li>
      <li style="display:flex;align-items:flex-start;gap:8px">
        <span style="color:#0052CC;font-weight:bold">✓</span>
        <div><strong>Pago de Cuotas con VEP / QR:</strong> Generación instantánea de QR para pagar desde Mercado Pago o homebanking.</div>
      </li>
      <li style="display:flex;align-items:flex-start;gap:8px">
        <span style="color:#0052CC;font-weight:bold">✓</span>
        <div><strong>Facturador C Asistido:</strong> Emití comprobantes oficiales a clientes sin entrar al portal de AFIP.</div>
      </li>
      <li style="display:flex;align-items:flex-start;gap:8px">
        <span style="color:#0052CC;font-weight:bold">✓</span>
        <div><strong>Alta, Baja y Modificación Registral:</strong> Cese por actividad o alta de nuevo servicio con F. 152 al instante.</div>
      </li>
    </ul>
    <a class="btn sm sec" href="/mcp" style="margin-top:auto">Conectar Monotributo →</a>
  </div>
</div>

<!-- KICKOFF INTELIGENTE: LAS 5 COORDENADAS DEL NEGOCIO -->
<div class="card" style="background:#F6F9FC;border:1px solid #DCE4EC;border-radius:14px;padding:26px 30px;margin:28px 0">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
    <span style="font-size:28px">🎯</span>
    <div>
      <h3 style="margin:0;font-size:20px;color:var(--ink)">Kickoff Inteligente: La IA aprende el ADN fiscal de tu negocio en 30 segundos</h3>
      <p style="margin:2px 0 0;color:var(--muted);font-size:14.5px">Sin formularios eternos ni planillas contables complejas. Al conectar, tu IA solo te pide 5 respuestas en lenguaje cotidiano:</p>
    </div>
  </div>
  <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-top:16px">
    <div style="background:#fff;border:1px solid #E2E8F0;border-radius:10px;padding:14px">
      <div style="color:#0B6E4F;font-weight:700;font-size:12.5px;margin-bottom:4px">1. TU ROL & PERSONERÍA</div>
      <p style="margin:0;font-size:13.5px;color:var(--ink)">Monotributo, Responsable Inscripto o Sociedad (S.R.L. / S.A.).</p>
    </div>
    <div style="background:#fff;border:1px solid #E2E8F0;border-radius:10px;padding:14px">
      <div style="color:#0B6E4F;font-weight:700;font-size:12.5px;margin-bottom:4px">2. QUÉ VENDÉS</div>
      <p style="margin:0;font-size:13.5px;color:var(--ink)">Servicios, comercio, software, consultoría o productos físicos.</p>
    </div>
    <div style="background:#fff;border:1px solid #E2E8F0;border-radius:10px;padding:14px">
      <div style="color:#0B6E4F;font-weight:700;font-size:12.5px;margin-bottom:4px">3. A QUIÉN LE VENDÉS</div>
      <p style="margin:0;font-size:13.5px;color:var(--ink)">Empresas (Factura A), Consumidor Final (Factura B/C) o Exterior (Factura E).</p>
    </div>
    <div style="background:#fff;border:1px solid #E2E8F0;border-radius:10px;padding:14px">
      <div style="color:#0B6E4F;font-weight:700;font-size:12.5px;margin-bottom:4px">4. UBICACIÓN & VENTAS</div>
      <p style="margin:0;font-size:13.5px;color:var(--ink)">Dónde estás y si despachás a otras provincias para blindarte de retenciones bancarias (SIRCREB).</p>
    </div>
    <div style="background:#fff;border:1px solid #E2E8F0;border-radius:10px;padding:14px">
      <div style="color:#0B6E4F;font-weight:700;font-size:12.5px;margin-bottom:4px">5. EMPLEADOS EN BLANCO</div>
      <p style="margin:0;font-size:13.5px;color:var(--ink)">0 empleados (costo patronal $0) o equipo con nómina (F. 931, Libro Digital y ART).</p>
    </div>
  </div>
  <div style="margin-top:16px;background:#E7F3EE;border-left:4px solid #0B6E4F;padding:10px 16px;border-radius:0 8px 8px 0;font-size:14px;color:#08523B">
    💡 <strong>Resultado inmediato:</strong> La IA encuadra tu negocio, asigna tus comprobantes y te entrega análisis claros y accionables en lenguaje directo, siempre respaldados por la normativa vigente.
  </div>
</div>

<!-- NOVEDADES DIARIAS, MORATORIAS Y BLANQUEO EN LENGUAJE SIMPLE -->
<div style="background:#fff;border:1px solid #E2E8F0;border-radius:14px;padding:26px 30px;margin:28px 0;box-shadow:0 4px 20px rgba(0,0,0,0.03)">
  <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-bottom:16px">
    <div>
      <span class="kicker" style="color:#0B6E4F">Traductor Impositivo Diario</span>
      <h3 style="margin:4px 0 0;font-size:20px;color:var(--ink)">Moratorias, Blanqueos y Planes de Pago: qué significan y cómo aprovecharlos en tu negocio</h3>
    </div>
    <span style="background:#E7F3EE;color:#0B6E4F;font-weight:700;font-size:12px;padding:4px 10px;border-radius:99px">ACTUALIZACIÓN DIARIA ARCA</span>
  </div>
  <p style="color:var(--muted);font-size:14.5px;margin:0 0 16px">Cada vez que el gobierno o ARCA publican una nueva resolución en el Boletín Oficial, tu IA la traduce a impacto financiero real: te dice si te sirve para bajar costos, financiar pasivos o regularizar tu situación.</p>
  
  <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px">
    <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;padding:16px">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
        <span style="font-size:20px">⚖️</span>
        <strong style="color:var(--ink);font-size:15px">Moratoria Fiscal (Ley 27.743)</strong>
      </div>
      <p style="font-size:13.5px;color:var(--muted);margin:0 0 8px"><strong>En concreto:</strong> Regularizás deudas vencidas de Monotributo, IVA, Ganancias o cargas sociales pagando solo el capital original, con condonación de multas y hasta el 100% de los intereses acumulados.</p>
      <div style="font-size:12.5px;color:#0B6E4F;font-weight:600">✓ Quita de intereses y financiación en hasta 84 cuotas.</div>
    </div>

    <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;padding:16px">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
        <span style="font-size:20px">🏦</span>
        <strong style="color:var(--ink);font-size:15px">Blanqueo de Capitales (0%)</strong>
      </div>
      <p style="font-size:13.5px;color:var(--muted);margin:0 0 8px"><strong>En concreto:</strong> Permite exteriorizar ahorros o activos no declarados hasta USD 100.000 a alícuota 0%, dejándolos disponibles en el circuito formal para inversiones o compra de bienes sin contingencias pasadas.</p>
      <div style="font-size:12.5px;color:#0B6E4F;font-weight:600">✓ Tasa 0% y liberación de impuestos omitidos previos.</div>
    </div>

    <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;padding:16px">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
        <span style="font-size:20px">💳</span>
        <strong style="color:var(--ink);font-size:15px">Planes de Pago Permanentes (RG 5321)</strong>
      </div>
      <p style="font-size:13.5px;color:var(--muted);margin:0 0 8px"><strong>En concreto:</strong> Financian pasivos impositivos corrientes en cuotas mensuales con débito directo en CBU (día 16), permitiendo ordenar la caja y destrabar embargos o bloqueos registrales en 48 hs.</p>
      <div style="font-size:12.5px;color:#0B6E4F;font-weight:600">✓ Desbloqueo de CUIT y alivio inmediato del flujo de caja.</div>
    </div>
  </div>
</div>

<!-- HUMAN IN THE LOOP: REVISIÓN DE UN CONTADOR HUMANO MATRICULADO -->
<div class="card" style="background:linear-gradient(135deg, #0F1C2D 0%, #162B44 100%);color:#fff;border-radius:14px;padding:26px 30px;margin:28px 0;border:1px solid #233B56">
  <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:20px;flex-wrap:wrap">
    <div style="flex:1 1 500px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
        <span style="background:#0B6E4F;color:#4EFA9D;font-weight:800;font-size:12px;padding:4px 10px;border-radius:6px;letter-spacing:0.04em">HUMAN IN THE LOOP</span>
        <span style="color:#A0B3C6;font-size:13.5px">Tranquilidad jurídica 100% garantizada</span>
      </div>
      <h3 style="margin:0 0 10px;font-size:21px;color:#fff">Velocidad agéntica de IA + Respaldo de Contadores Públicos Matriculados</h3>
      <p style="margin:0 0 14px;color:#B8C8D9;font-size:15px;line-height:1.5">
        La IA realiza las liquidaciones, auditorías y cruces en segundos. Pero <strong>en todo momento podés pedir que un Contador Público Matriculado humano revise tu caso</strong> con un solo mensaje: <em>"Quiero que un contador revise este borrador"</em>.
      </p>
      <div style="display:flex;gap:16px;flex-wrap:wrap;font-size:13.5px;color:#4EFA9D">
        <div>✓ Revisión profesional en menos de 2 horas hábiles</div>
        <div>✓ Doble chequeo antes de cualquier presentación definitiva en ARCA</div>
        <div>✓ Certificaciones contables con legalización de Consejo Profesional</div>
      </div>
    </div>
    <div style="display:flex;flex-direction:column;gap:10px;justify-content:center">
      <a class="btn" href="/mcp" style="background:#0B6E4F;color:#fff;border:0;padding:12px 22px;font-weight:700">Probar con tu CUIT gratis →</a>
      <span style="color:#8EA2B6;font-size:12px;text-align:center">Sin tarjetas de crédito · Cancelás cuando quieras</span>
    </div>
  </div>
</div>

<!-- BLINDAJE FEDERAL: JURISPRUDENCIA CSJN, 24 PROVINCIAS Y MUNICIPIOS -->
<div style="background:#F6F9FC;border:1px solid #D5E0EB;border-radius:14px;padding:26px 30px;margin:28px 0">
  <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-bottom:12px">
    <div>
      <span class="kicker" style="color:#0B6E4F">Blindaje Federal & Defensa Constitucional</span>
      <h3 style="margin:4px 0 0;font-size:20px;color:var(--ink)">Jurisprudencia de la Corte Suprema y Políticas de 24 Provincias y Municipios</h3>
    </div>
    <span style="background:#E7F3EE;color:#0B6E4F;font-weight:700;font-size:12px;padding:4px 10px;border-radius:99px">CSJN · ARBA · AGIP · SIFERE</span>
  </div>
  <p style="color:var(--muted);font-size:14.5px;margin:0 0 18px">En Argentina los impuestos no son solo nacionales: provincias y municipios inventan tasas y retenciones todos los meses. Tu IA conoce la jurisprudencia líder de la Corte Suprema para frenar cobros abusivos y proteger tu caja:</p>

  <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px">
    <div style="background:#fff;border:1px solid #E2E8F0;border-radius:10px;padding:16px">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
        <span style="font-size:18px">🏛️</span>
        <strong style="color:var(--ink);font-size:14.5px">Tasas Municipales (Fallo Raffo / Esso)</strong>
      </div>
      <p style="font-size:13px;color:var(--muted);margin:0 0 8px"><em>"Si vendés por internet o mandás una encomienda pero no tenés local físico en ese municipio, el intendente no puede cobrarte tasa de inspección."</em></p>
      <div style="font-size:12px;color:#0B6E4F;font-weight:600">Escudo contra intimaciones de TISH sin sustento territorial.</div>
    </div>

    <div style="background:#fff;border:1px solid #E2E8F0;border-radius:10px;padding:16px">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
        <span style="font-size:18px">📉</span>
        <strong style="color:var(--ink);font-size:14.5px">Tope a la Confiscatoriedad (Fallo Candy)</strong>
      </div>
      <p style="font-size:13px;color:var(--muted);margin:0 0 8px"><em>"Si la inflación hace que el impuesto te coma más del 33% al 35% de lo que ganaste realmente en mano, la Corte Suprema te da la razón y frena a ARCA."</em></p>
      <div style="font-size:12px;color:#0B6E4F;font-weight:600">Ajuste por Inflación Impositivo integral asegurado.</div>
    </div>

    <div style="background:#fff;border:1px solid #E2E8F0;border-radius:10px;padding:16px">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
        <span style="font-size:18px">🚫</span>
        <strong style="color:var(--ink);font-size:14.5px">Alícuotas Discriminatorias (Fallo Bayer)</strong>
      </div>
      <p style="font-size:13px;color:var(--muted);margin:0 0 8px"><em>"Una provincia no puede cobrarle más caro de Ingresos Brutos a una fábrica solo porque está radicada en otra provincia. La Constitución prohíbe aduanas interiores."</em></p>
      <div style="font-size:12px;color:#0B6E4F;font-weight:600">Reclamo de devolución de retenciones provinciales agravadas.</div>
    </div>

    <div style="background:#fff;border:1px solid #E2E8F0;border-radius:10px;padding:16px">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
        <span style="font-size:18px">🛡️</span>
        <strong style="color:var(--ink);font-size:14.5px">Embargos sin Orden Judicial (Intercorp)</strong>
      </div>
      <p style="font-size:13px;color:var(--muted);margin:0 0 8px"><em>"ARCA no puede apretar un botón y congelar tu cuenta del banco sola: necesita obligatoriamente que un juez neutral firme la orden de embargo."</em></p>
      <div style="font-size:12px;color:#0B6E4F;font-weight:600">Defensa cautelar inmediata ante amenazas de trabas bancarias.</div>
    </div>
  </div>
  
  <div style="margin-top:16px;background:#fff;border-left:4px solid #0B6E4F;padding:12px 16px;border-radius:0 8px 8px 0;font-size:13.5px;color:var(--ink)">
    📍 <strong>Cobertura Federal Integral:</strong> Reglas específicas para <strong>CABA (AGIP y Distrito Tecnológico)</strong>, <strong>PBA (ARBA y Monotributo Unificado)</strong>, <strong>Córdoba</strong>, <strong>Santa Fe</strong>, <strong>Mendoza</strong> y el <strong>Convenio Multilateral SIFERE</strong> para que nunca sufras retenciones dobles en tus cuentas bancarias por el padrón SIRCREB.
  </div>
</div>

<!-- DOCUMENTOS OFF-ARCA + REPORTES VISUALES CON GRÁFICOS -->
<div style="background:#fff;border:1px solid #DCE4EC;border-radius:14px;padding:28px 30px;margin:28px 0;box-shadow:0 6px 24px rgba(15,27,45,0.04)">
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:28px;align-items:center">
    <div>
      <span class="kicker" style="color:#0B6E4F">La Película Completa · Gráficos Claros</span>
      <h3 style="margin:6px 0 10px;font-size:21px;color:var(--ink);line-height:1.25">Adjuntá en el chat lo que ARCA no ve y recibí gráficos fáciles de entender</h3>
      <p style="margin:0 0 14px;color:var(--muted);font-size:14.5px;line-height:1.55">
        ARCA solo ve tus facturas electrónicas. Como un contador real, tu IA te pide arrastrar directamente en el chat (PDF, foto o Excel) los comprobantes complementarios para armar la película completa y rescatar cada peso de ahorro:
      </p>
      <ul style="list-style:none;padding:0;margin:0 0 16px;display:grid;gap:8px;font-size:14px;color:var(--ink)">
        <li>📎 <strong>Resúmenes de banco y Mercado Pago:</strong> recupera Impuesto al Cheque (MiPyME), IVA de comisiones y frena SIRCREB.</li>
        <li>💳 <strong>Tarjetas de crédito:</strong> rescata percepciones del 30% y deduce servicios del exterior (AWS, Meta, Google, OpenAI).</li>
        <li>🛡️ <strong>Seguros, prepaga, alquileres y tickets:</strong> deduce gastos no registrados en ARCA (Art. 83) y baja tu impuesto.</li>
        <li>👥 <strong>Novedades de empleados:</strong> horas extras, licencias y póliza de ART directo en el chat para tu F. 931.</li>
      </ul>
      <div style="background:#E7F3EE;border-left:4px solid #0B6E4F;padding:10px 14px;border-radius:0 8px 8px 0;font-size:13.5px;color:#08523B">
        📊 <strong>Sin planillas indescifrables:</strong> cada resultado llega con <strong>gráficos de torta, barras comparativas y semáforos visuales</strong> para que entiendas tu plata en 5 segundos.
      </div>
    </div>

    <!-- VISTA PREVIA VISUAL DEL REPORTE (ILUSTRACIÓN SVG REAL) -->
    <div style="background:#0F1B2D;border-radius:12px;padding:22px;color:#fff;border:1px solid #1E3148">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
        <span style="font-size:12px;font-weight:700;color:#4EFA9D;letter-spacing:0.05em">REPORTE VISUAL · EJEMPLO IMAGINARIO</span>
        <span style="background:#1A2E46;color:#8FD3B6;font-size:11px;padding:3px 8px;border-radius:99px">+$292.000 ahorrados</span>
      </div>
      <div style="font-size:14.5px;font-weight:700;margin-bottom:14px;color:#fff">¿A dónde va cada peso que facturaste este mes? ($5.000.000)</div>

      <!-- Gráfico de torta SVG + Leyenda -->
      <div style="display:flex;align-items:center;gap:18px;flex-wrap:wrap;margin-bottom:18px">
        <svg width="112" height="112" viewBox="0 0 36 36" aria-label="Distribución de facturación mensual">
          <circle cx="18" cy="18" r="15.915" fill="transparent" stroke="#1E3148" stroke-width="5"></circle>
          <circle cx="18" cy="18" r="15.915" fill="transparent" stroke="#0B6E4F" stroke-width="5" stroke-dasharray="51 49" stroke-dashoffset="25"></circle>
          <circle cx="18" cy="18" r="15.915" fill="transparent" stroke="#3B82F6" stroke-width="5" stroke-dasharray="33 67" stroke-dashoffset="-26"></circle>
          <circle cx="18" cy="18" r="15.915" fill="transparent" stroke="#F59E0B" stroke-width="5" stroke-dasharray="10 90" stroke-dashoffset="-59"></circle>
          <circle cx="18" cy="18" r="15.915" fill="transparent" stroke="#4EFA9D" stroke-width="5" stroke-dasharray="6 94" stroke-dashoffset="-69"></circle>
          <text x="18" y="19.5" text-anchor="middle" fill="#fff" font-size="5.5" font-weight="700">51%</text>
        </svg>
        <div style="flex:1;min-width:150px;display:grid;gap:6px;font-size:12.5px">
          <div style="display:flex;justify-content:space-between"><span><span style="color:#0B6E4F">●</span> Tu bolsillo limpio</span><strong>$2.527.000</strong></div>
          <div style="display:flex;justify-content:space-between"><span><span style="color:#3B82F6">●</span> Gastos (ARCA + adjuntos)</span><strong>$1.650.000</strong></div>
          <div style="display:flex;justify-content:space-between"><span><span style="color:#F59E0B">●</span> Impuestos netos finales</span><strong>$531.000</strong></div>
          <div style="display:flex;justify-content:space-between;color:#4EFA9D"><span>● Ahorro rescatado PDFs</span><strong>+$292.000</strong></div>
        </div>
      </div>

      <!-- Comparativa de barras Antes vs Después de adjuntar -->
      <div style="border-top:1px solid #1E3148;padding-top:12px;font-size:12px">
        <div style="color:#9AAFC6;margin-bottom:8px;font-weight:600">Impacto de adjuntar tus extractos de banco y tarjeta:</div>
        <div style="margin-bottom:6px">
          <div style="display:flex;justify-content:space-between;margin-bottom:3px"><span style="color:#CBD5E1">Solo con datos de ARCA</span><span style="color:#F87171">$1.200.000</span></div>
          <div style="background:#1E3148;height:8px;border-radius:99px;overflow:hidden"><div style="background:#F87171;width:100%;height:100%"></div></div>
        </div>
        <div>
          <div style="display:flex;justify-content:space-between;margin-bottom:3px"><span style="color:#CBD5E1">Con tus adjuntos conciliados</span><span style="color:#4EFA9D">$531.000 (-55%)</span></div>
          <div style="background:#1E3148;height:8px;border-radius:99px;overflow:hidden"><div style="background:#4EFA9D;width:45%;height:100%"></div></div>
        </div>
      </div>
    </div>
  </div>
</div>
</section>

<section class="wrap" style="padding-top:24px">
<div class="tool" style="margin:0;display:flex;flex-wrap:wrap;gap:20px;align-items:center;justify-content:space-between">
<div style="flex:1 1 480px;min-width:0"><span class="kicker">Herramienta gratis · nueva</span>
<h2 style="margin:6px 0 6px">¿Cuánto IVA vas a pagar este mes?</h2>
<p style="margin:0;color:var(--muted)">Conectá tu CUIT una vez: nuestro robot consulta ARCA y te dice cuánto viene antes del vencimiento, para planificar compras sin llamar a tu contador.</p></div>
<a class="btn" href="/iva/">Calcular mi IVA</a>
</div>
</section>

<section class="wrap" style="padding-top:28px">
<div class="grid">
<a class="card" href="/iibb/"><h3>Ingresos Brutos</h3><p>Simulador de coeficientes del Convenio Multilateral, alícuotas de padrón y SIRCREB.</p><span class="go">Abrir →</span></a>
<a class="card" href="/ganancias/"><h3>Ganancias</h3><p>¿Pagás anticipos de más? Calculá cuánta caja podés liberar este ejercicio.</p><span class="go">Abrir →</span></a>
<a class="card" href="/retenciones/"><h3>Retenciones y percepciones</h3><p>Test: ¿te están reteniendo de más? Exclusión, reducción y recupero.</p><span class="go">Abrir →</span></a>
</div>
</section>

<section class="dark" id="empresas" style="margin-top:56px"><div class="wrap sec-pad">
<span class="kicker">Para empresas medianas</span>
<h2 style="margin-top:6px;max-width:760px">Impuestos que te hacen más competitivo</h2>
<p style="max-width:760px;font-size:18px">Tu equipo de impuestos está ocupado cumpliendo vencimientos. Una segunda opinión independiente mira lo que el día a día no deja ver: saldos a favor que crecen, alícuotas mal asignadas, beneficios sin usar y contingencias antes de que lleguen.</p>
<div class="grid" style="margin-top:24px">
<a class="card" href="/empresas/saldos-a-favor/"><h3>¿Cuánta plata tenés atrapada en saldos a favor?</h3><p>Retenciones y percepciones de IIBB e IVA que se acumulan y nadie gestiona.</p><span class="go">Estimar mi saldo →</span></a>
<a class="card" href="/empresas/auditoria-de-estados-contables/"><h3>¿Tu empresa necesita auditar sus balances?</h3><p>IGJ, bancos, SGR, licitaciones o casa matriz. Test y cotización.</p><span class="go">Hacer el test →</span></a>
<a class="card" href="/empresas/fiscalizacion-arca/"><h3>¿Resistirías una fiscalización de ARCA?</h3><p>Checklist de 8 puntos para encontrar contingencias antes que el fisco.</p><span class="go">Revisar mi riesgo →</span></a>
<a class="card" href="/empresas/"><h3>¿Qué no te está diciendo tu departamento de impuestos?</h3><p>Planificación fiscal, Convenio Multilateral y precios de transferencia.</p><span class="go">Ver todo para empresas →</span></a>
</div>
</div></section>

<section class="wrap sec-pad" id="responsables-inscriptos">
<span class="kicker">Para responsables inscriptos y profesionales</span>
<h2 style="margin-top:6px">Pagá lo justo, en el momento justo</h2>
<div class="grid">
<a class="card" href="/iva/"><h3>Calculadora de IVA del mes</h3><p>Débito, crédito, retenciones y saldo a pagar con tus comprobantes de ARCA.</p><span class="go">Calcular →</span></a>
<a class="card" href="/responsables-inscriptos/"><h3>Dónde pierde plata un responsable inscripto</h3><p>Créditos que se corren, anticipos de más, saldos a favor sin reclamar.</p><span class="go">Leer la guía →</span></a>
<a class="card" href="/contador/tu-contador-lo-hace-bien/"><h3>¿Tu contador está haciendo bien las cosas?</h3><p>Test de 8 preguntas para saber si conviene una segunda opinión.</p><span class="go">Hacer el test →</span></a>
</div>
<p style="margin-top:20px;color:var(--muted)">¿Sos monotributista? Mirá la <a href="/monotributo/categorias/">calculadora de categorías</a> o si te conviene <a href="/monotributo/monotributo-o-responsable-inscripto/">pasar a responsable inscripto</a>.</p>
</section>

<section class="wrap" style="padding-bottom:24px">
<div class="tool" style="margin:0">
<span class="kicker">Datos clave hoy · actualizado el {C.UPDATED_HUMAN}</span>
<div class="grid" style="margin-top:14px">
<div><strong style="font-size:26px">21%</strong><p style="margin:4px 0 0;color:var(--muted)">Alícuota general de IVA (10,5% reducida; 27% para ciertos servicios a responsables inscriptos).</p></div>
<div><strong style="font-size:26px">$3.000 millones</strong><p style="margin:4px 0 0;color:var(--muted)">Umbral del estudio de <a href="/empresas/precios-de-transferencia/">precios de transferencia</a> (RG 5903/2026).</p></div>
<div><strong style="font-size:26px">4 meses</strong><p style="margin:4px 0 0;color:var(--muted)">Plazo habitual para aprobar los <a href="/empresas/auditoria-de-estados-contables/">estados contables</a> de una sociedad por acciones.</p></div>
<div><strong style="font-size:26px">{money(K['tope'])}</strong><p style="margin:4px 0 0;color:var(--muted)">Tope del monotributo: por encima, se pasa a <a href="/responsables-inscriptos/">responsable inscripto</a>.</p></div>
</div></div>
</section>

<section class="wrap sec-pad">
<h2 style="margin-top:0">Cómo funciona</h2>
<div class="steps">
<div><h3>Contanos tu caso</h3><p>Respondés 4 preguntas. No hace falta tener papeles a mano.</p></div>
<div><h3>Te asignamos el especialista indicado</h3><p>Según tu perfil, te conectamos con el estudio aliado que mejor resuelve ese tipo de casos.</p></div>
<div><h3>Recibís un diagnóstico y una propuesta</h3><p>Te dicen qué conviene corregir y cuánto cuesta. Vos decidís si avanzás.</p></div>
</div>
</section>

<section class="wrap" style="padding-bottom:72px;max-width:860px">
<h2>Preguntas frecuentes</h2>
{faq_html(HOME_FAQS)}
<p style="margin-top:24px"><a class="btn" href="/diagnostico/">Empezar mi diagnóstico gratis</a></p>
</section>
"""

PAGES.append(dict(
    path="/", kind="custom",
    title=f"{C.SITE_NAME} — Impuestos bien llevados que te hacen ganar plata",
    og_title="¿Qué no te está diciendo tu contador?",
    description="Segunda opinión gratis sobre tus impuestos: IVA, Ganancias, saldos a favor, auditoría y fiscalizaciones de ARCA. Calculadora de IVA del mes y diagnóstico.",
    h1="Tus impuestos bien llevados te hacen ganar plata",
    answer=f"<p>{C.SITE_NAME} explica los impuestos en Argentina con datos actualizados y ofrece un diagnóstico gratuito que conecta a personas y empresas con estudios contables aliados.</p>",
    body=HOME, faqs=HOME_FAQS,
))

PAGES.append(dict(
    path="/diagnostico/", kind="custom", crumbs=[("Diagnóstico gratis", "/diagnostico/")],
    title="Diagnóstico impositivo gratis: segunda opinión en 2 minutos",
    description="Respondé 4 preguntas y un especialista revisa tus impuestos: IVA, Ganancias, saldos a favor, auditoría o fiscalizaciones de ARCA. Gratis y sin compromiso.",
    h1="Diagnóstico impositivo gratis",
    body=f"""<div class="wrap layout" style="padding-top:20px">
<div class="main"><h1>Diagnóstico impositivo gratis</h1>
<p class="lead">Una segunda opinión sobre tus impuestos en 2 minutos. Te contactamos dentro de {C.PLAZO_RESPUESTA}.</p>
{diag_widget()}</div>
<aside class="side"><div class="tool" style="margin-top:0"><h2 style="font-size:20px;margin:0 0 10px">Qué vas a recibir</h2>
<ul class="checks"><li>Una revisión de tu situación por un contador matriculado</li><li>Qué conviene corregir y qué podés recuperar</li><li>Una propuesta de honorarios clara, si querés avanzar</li></ul>
<h2 style="font-size:20px;margin:20px 0 10px">Lo que nunca vamos a hacer</h2>
<ul class="checks"><li>Pedirte la clave fiscal para el diagnóstico</li><li>Compartir tus datos sin tu consentimiento</li><li>Cobrarte por el diagnóstico</li></ul>
<p class="src" style="margin-top:16px">Podés pedir diagnóstico sin cargo o revisión de un contador público matriculado.</p></div></aside>
</div>""",
))

PAGES.append(dict(
    path="/gracias/", kind="custom", noindex=True, crumbs=[("Gracias", "/gracias/")],
    title="¡Recibimos tu consulta!", description="Tu consulta fue enviada.", h1="¡Recibimos tu consulta!",
    body=f"""<div class="wrap" style="max-width:760px;padding:40px 20px 80px">
<h1>¡Listo! Recibimos tu consulta</h1>
<p class="lead">Un especialista te va a contactar dentro de {C.PLAZO_RESPUESTA}, por WhatsApp o email.</p>
<div class="tool"><h2 style="margin:0 0 10px;font-size:21px">Para aprovechar la reunión, tené a mano:</h2>
<ul class="checks"><li>Tu CUIT (no la clave fiscal)</li><li>Lo facturado en los últimos 12 meses, aunque sea aproximado</li><li>Cualquier notificación de ARCA o rentas provinciales que hayas recibido</li></ul></div>
<p>Mientras tanto: <a href="/monotributo/categorias/">calculá tu categoría de monotributo</a> o revisá el <a href="/calendario-fiscal/">calendario de vencimientos</a>.</p>
</div>""",
))

PAGES.append(dict(
    path="/herramientas/", kind="article", crumbs=[("Herramientas", "/herramientas/")],
    title="Calculadoras y tests de impuestos gratis",
    description="Herramientas gratis: calculadora de IVA del mes, estimador de saldos a favor, test de auditoría, riesgo ante ARCA, test de tu contador y monotributo.",
    h1="Calculadoras y tests de impuestos gratis",
    answer="<p>Herramientas gratuitas, sin registro: calculá <a href=\"/iva/\">cuánto IVA vas a pagar este mes</a>, tu <a href=\"/monotributo/categorias/\">categoría de monotributo</a>, evaluá a <a href=\"/contador/tu-contador-lo-hace-bien/\">tu contador</a>, estimá tus <a href=\"/empresas/saldos-a-favor/\">saldos a favor</a>, averiguá si tu empresa <a href=\"/empresas/auditoria-de-estados-contables/\">necesita auditoría</a> y medí tu <a href=\"/empresas/fiscalizacion-arca/\">riesgo ante ARCA</a>.</p>",
    body="""<div class="grid">
<a class="card" href="/iva/"><h3>IVA del mes, automático</h3><p>Conectá tu CUIT y sabé cuánto IVA viene antes del vencimiento.</p><span class="go">Abrir →</span></a>
<a class="card" href="/iibb/"><h3>Simulador del Convenio Multilateral</h3><p>Coeficientes unificados y base imponible por provincia.</p><span class="go">Abrir →</span></a>
<a class="card" href="/ganancias/"><h3>Anticipos de Ganancias</h3><p>Cuánto estás adelantando de más y cuánta caja podés liberar.</p><span class="go">Abrir →</span></a>
<a class="card" href="/retenciones/"><h3>¿Te retienen de más?</h3><p>Test de 6 preguntas sobre retenciones y percepciones.</p><span class="go">Abrir →</span></a>
<a class="card" href="/monotributo/categorias/"><h3>Calculadora de monotributo</h3><p>Tu categoría y cuota con la tabla vigente, y cuánto podrías ahorrar.</p><span class="go">Abrir →</span></a>
<a class="card" href="/contador/tu-contador-lo-hace-bien/"><h3>¿Tu contador lo hace bien?</h3><p>8 preguntas para saber si conviene una segunda opinión.</p><span class="go">Abrir →</span></a>
<a class="card" href="/empresas/saldos-a-favor/"><h3>Estimador de saldos a favor</h3><p>Cuánto capital inmovilizan las retenciones y percepciones.</p><span class="go">Abrir →</span></a>
<a class="card" href="/empresas/auditoria-de-estados-contables/"><h3>¿Necesitás auditoría?</h3><p>Test de 6 preguntas para empresas.</p><span class="go">Abrir →</span></a>
<a class="card" href="/empresas/fiscalizacion-arca/"><h3>Riesgo ante una fiscalización</h3><p>Checklist de 8 controles clave.</p><span class="go">Abrir →</span></a>
</div>""",
    related=["/calendario-fiscal/", "/glosario/"],
))

PAGES.append(dict(
    path="/calendario-fiscal/", kind="article", crumbs=[("Calendario fiscal", "/calendario-fiscal/")],
    title="Calendario fiscal 2026-2027: vencimientos clave",
    description=f"Vencimientos clave: cuota del monotributo (día 20), recategorización ({RECAT}), IVA, Ingresos Brutos, Ganancias y balances.",
    h1="Calendario fiscal: vencimientos clave para monotributistas y empresas",
    about=["Vencimientos impositivos", "Calendario fiscal ARCA"],
    answer=(f"<p>La cuota del monotributo vence el <strong>día 20 de cada mes</strong>; la próxima recategorización vence el <strong>{RECAT}</strong> y la tabla actual rige hasta el "
            "31 de enero de 2027. IVA, Ingresos Brutos y cargas sociales vencen cada mes según la <strong>terminación del CUIT</strong>: confirmá tu fecha exacta en el calendario oficial de ARCA y de tu provincia.</p>"),
    body=f"""
<h2>Monotributistas</h2>
{table(["Obligación", "Vencimiento"], [
        ["Cuota mensual", "Día 20 de cada mes (o hábil siguiente)"],
        ["Recategorización de enero", f"{RECAT} (ingresos enero–diciembre 2026)"],
        ["Nueva tabla de categorías", "Febrero de 2027 (actualización semestral)"],
        ["Recategorización de julio", "Principios de agosto de 2027"],
    ])}
<h2>Responsables inscriptos y empresas</h2>
{table(["Obligación", "Frecuencia", "Referencia"], [
        ["IVA (declaración y pago)", "Mensual", "Según terminación de CUIT"],
        ["Cargas sociales (F.931)", "Mensual", "Según terminación de CUIT"],
        ["Ingresos Brutos / Convenio Multilateral", "Mensual", "Calendario provincial o de la Comisión Arbitral"],
        ["Ganancias y Bienes Personales (personas humanas)", "Anual", "A mitad de año, según cronograma de ARCA"],
        ["Ganancias sociedades", "Anual", "Quinto mes posterior al cierre del ejercicio"],
        ["Asamblea y estados contables (sociedades por acciones)", "Anual", "Dentro de los 4 meses del cierre"],
        ["Precios de transferencia (F.2668 y estudio)", "Anual", "Meses posteriores al cierre, según RG 5903/2026"],
    ], caption="Referencia orientativa. Las fechas exactas dependen del CUIT, la jurisdicción y el cierre de ejercicio.")}
{cta("persona", None, "¿Querés que alguien controle tus vencimientos?", "Un contador de un estudio aliado se ocupa de las fechas y te avisa antes.")}""",
    faqs=[
        ("¿Cuándo vence el monotributo este mes?", "El día 20, o el primer día hábil siguiente si cae en feriado o fin de semana."),
        ("¿Dónde veo mis vencimientos exactos?", "En el calendario de vencimientos de ARCA, filtrando por impuesto y terminación de CUIT, y en el sitio de la agencia de recaudación de tu provincia."),
    ],
    sources=[("ARCA — Calendario de vencimientos", "https://www.arca.gob.ar/vencimientos/"), ARCA_MONO, COMARB],
    related=["/monotributo/recategorizacion/", "/monotributo/categorias/"],
))

GLOS = [
    ("ARCA", "Agencia de Recaudación y Control Aduanero. Reemplazó a la AFIP en 2024 y administra los impuestos nacionales, la seguridad social y la aduana."),
    ("Monotributo", "Régimen Simplificado para Pequeños Contribuyentes: una cuota mensual que incluye impuesto integrado, jubilación y obra social. Ver <a href=\"/monotributo/\">guía</a>."),
    ("Recategorización", "Revisión semestral (enero y julio) de la categoría del monotributo según los últimos 12 meses. Ver <a href=\"/monotributo/recategorizacion/\">guía</a>."),
    ("Exclusión del monotributo", "Baja del régimen simplificado por superar topes u otras causales, con alta en IVA y Ganancias. Ver <a href=\"/monotributo/exclusion/\">guía</a>."),
    ("Responsable inscripto", "Contribuyente del régimen general inscripto en IVA y Ganancias."),
    ("Factura C", "Comprobante que emiten los monotributistas; no discrimina IVA."),
    ("Domicilio Fiscal Electrónico", "Casilla digital obligatoria donde ARCA notifica intimaciones, fiscalizaciones y exclusiones. Los plazos corren aunque no la leas."),
    ("Clave fiscal", "Contraseña personal para operar en ARCA. No debe compartirse: se delegan servicios al contador."),
    ("Delegación de servicios", "Autorización que das desde el Administrador de Relaciones de ARCA para que un tercero opere en tu nombre."),
    ("Ingresos Brutos", "Impuesto provincial sobre la facturación de la actividad."),
    ("Convenio Multilateral", "Acuerdo que reparte la base de Ingresos Brutos entre provincias cuando se opera en varias. Ver <a href=\"/empresas/convenio-multilateral/\">guía</a>."),
    ("Coeficiente unificado", "Porcentaje que corresponde a cada provincia en el Convenio Multilateral, según ingresos y gastos del ejercicio anterior."),
    ("SIRCREB", "Sistema de recaudación de Ingresos Brutos sobre las acreditaciones bancarias."),
    ("Retención", "Parte del impuesto que te descuenta quien te paga, como anticipo."),
    ("Percepción", "Parte del impuesto que te cobra adicionalmente quien te vende, como anticipo."),
    ("Saldo a favor", "Exceso de retenciones, percepciones o anticipos sobre el impuesto determinado. Ver <a href=\"/empresas/saldos-a-favor/\">guía</a>."),
    ("Saldo de libre disponibilidad", "Saldo a favor de IVA originado en retenciones, percepciones o pagos a cuenta; puede compensarse o pedirse en devolución según el caso."),
    ("Saldo técnico de IVA", "Exceso de crédito fiscal por compras sobre el débito fiscal por ventas; en general se traslada a períodos siguientes."),
    ("Precios de transferencia", "Régimen que exige valores de mercado en operaciones con vinculadas del exterior. Ver <a href=\"/empresas/precios-de-transferencia/\">guía</a>."),
    ("Auditoría externa", "Revisión independiente de los estados contables por un contador público, que emite un informe con su opinión. Ver <a href=\"/empresas/auditoria-de-estados-contables/\">guía</a>."),
    ("IGJ", "Inspección General de Justicia: registro y control de sociedades en la Ciudad de Buenos Aires."),
    ("Artículo 299 (LGS)", "Artículo de la Ley General de Sociedades que somete a fiscalización estatal permanente a ciertas sociedades por acciones."),
    ("SAS", "Sociedad por Acciones Simplificada, tipo societario creado por la Ley 27.349."),
    ("NIIF", "Normas Internacionales de Información Financiera, usadas a menudo en el reporting a casas matrices del exterior."),
    ("IVA Simple", "Sistema de ARCA para liquidar y presentar la declaración jurada mensual de IVA, que toma los comprobantes electrónicos y reemplazó al Libro IVA Digital."),
    ("Débito fiscal", "IVA que facturás en tus ventas. Ver <a href=\"/iva/\">calculadora de IVA</a>."),
    ("Crédito fiscal", "IVA de tus compras con factura A, que descontás del débito fiscal."),
    ("F.931", "Declaración jurada mensual de cargas sociales del empleador."),
]
PAGES.append(dict(
    path="/glosario/", kind="article", crumbs=[("Glosario", "/glosario/")],
    title="Glosario de impuestos en Argentina: términos explicados",
    description="Glosario de impuestos: ARCA, monotributo, recategorización, Ingresos Brutos, Convenio Multilateral, saldos a favor, precios de transferencia, auditoría y más.",
    h1="Glosario de impuestos en Argentina",
    answer="<p>Definiciones breves y en lenguaje simple de los términos impositivos que más aparecen en Argentina, con enlaces a guías completas.</p>",
    body='<dl>' + "".join(f'<dt id="{t.lower().replace(" ", "-").replace("(", "").replace(")", "")}" style="font-weight:700;margin-top:18px">{t}</dt><dd style="margin:4px 0 0">{d}</dd>' for t, d in GLOS) + '</dl>',
    related=["/monotributo/", "/empresas/", "/herramientas/"],
    schema=[{"@type": "DefinedTermSet", "name": "Glosario de impuestos en Argentina", "url": C.SITE_URL + "/glosario/",
             "hasDefinedTerm": [{"@type": "DefinedTerm", "name": t, "description": d.split("<a")[0].strip()} for t, d in GLOS]}],
))

REV = C.REVISOR
rev_html = (f"<p><strong>{esc(REV['nombre'])}</strong>, {esc(REV.get('titulo', ''))}, {esc(REV.get('matricula', ''))}. {esc(REV.get('bio', ''))}</p>" if REV else
            "<p>El contenido técnico es revisado por contadores públicos matriculados de los estudios aliados antes de publicarse. Sus datos se publican en esta página.</p>")
PAGES.append(dict(
    path="/quienes-somos/", kind="about", crumbs=[("Quiénes somos", "/quienes-somos/")],
    title="Quiénes somos", description=f"{C.SITE_NAME} explica los impuestos en Argentina con datos oficiales y conecta a personas y empresas con estudios contables aliados.",
    h1="Quiénes somos",
    body=f"""<p>{C.SITE_NAME} nació para que los impuestos dejen de ser una caja negra. Creemos que bien llevados no son solo un costo: son plata que vuelve a tu bolsillo o a tu empresa.</p>
<h2>Qué hacemos</h2>
<ul><li>Publicamos guías claras, con cifras actualizadas y fuentes oficiales.</li><li>Ofrecemos herramientas gratuitas para revisar tu situación.</li><li>Te conectamos con el estudio contable aliado indicado para tu caso: {aliados_txt()}.</li></ul>
<h2>Quién revisa el contenido</h2>
{rev_html}
<h2>Contacto</h2>
<p>Escribinos a <a href="mailto:{C.EMAIL_CONTACTO}">{C.EMAIL_CONTACTO}</a>.</p>
<p>Titular del sitio: {C.TITULAR} · CUIT {C.CUIT}.</p>""",
))

PAGES.append(dict(
    path="/metodologia-editorial/", kind="page", crumbs=[("Metodología editorial", "/metodologia-editorial/")],
    title="Metodología editorial: cómo elaboramos el contenido",
    description="Cómo elaboramos y actualizamos el contenido: fuentes oficiales, revisión profesional, fechas de vigencia y corrección de errores.",
    h1="Metodología editorial",
    body="""<h2>Fuentes</h2><p>Usamos fuentes primarias: ARCA, Boletín Oficial, leyes y resoluciones, organismos provinciales y la Comisión Arbitral. Cada guía lista sus fuentes al final.</p>
<h2>Vigencia de las cifras</h2><p>Cada cifra indica desde cuándo y hasta cuándo rige. Las tablas del monotributo se actualizan cada vez que ARCA publica nuevos valores (febrero y agosto).</p>
<h2>Revisión profesional</h2><p>El contenido técnico lo revisa un contador público matriculado antes de publicarse y en cada actualización relevante.</p>
<h2>Independencia</h2><p>Nuestro criterio técnico es 100% independiente: no recomendamos pagar impuestos de más ni contratar servicios que no necesitás.</p>
<h2>Errores</h2><p>Si encontrás un error, escribinos. Lo corregimos y actualizamos la fecha de revisión.</p>""",
))

PAGES.append(dict(
    path="/privacidad/", kind="page", crumbs=[("Privacidad", "/privacidad/")],
    title="Política de privacidad", description="Cómo tratamos tus datos personales según la Ley 25.326 de Protección de Datos Personales.",
    h1="Política de privacidad",
    body=f"""<p>Última actualización: {C.UPDATED_HUMAN}.</p>
<h2>Responsable</h2><p>{C.TITULAR}, CUIT {C.CUIT}, contacto: <a href="mailto:{C.EMAIL_CONTACTO}">{C.EMAIL_CONTACTO}</a>. Base de datos registrada ante la Agencia de Acceso a la Información Pública: [N° DE REGISTRO].</p>
<h2>Qué datos recolectamos</h2><p>Los que completás en el diagnóstico (nombre, email, teléfono, provincia, empresa, cargo, facturación aproximada y tu consulta) y datos técnicos de navegación (página de origen, parámetros de campaña). No usamos cookies publicitarias.</p>
<h2>Para qué los usamos</h2><p>Para responder tu consulta y, con tu consentimiento expreso, cederlos al estudio contable aliado más adecuado ({aliados_txt()}) para que te contacte.</p>
<h2>Servicio de IVA automático</h2><p>Si usás este servicio, tratamos además tu CUIT, tu usuario de ARCA y tu clave fiscal, con tu autorización expresa y solo para consultar Mis Comprobantes. La clave se guarda cifrada (AES-256-GCM) únicamente si lo elegís y es procesada por un proveedor tecnológico que ejecuta la consulta. De tus comprobantes guardamos solo totales mensuales. Podés borrar tu cuenta y todos estos datos desde tu panel. Más detalle en <a href="/iva/seguridad/">cómo protegemos tu clave fiscal</a>.</p>
<h2>Cesión</h2><p>Solo cedemos tus datos al estudio aliado que corresponda a tu consulta, con tu consentimiento previo. No los vendemos.</p>
<h2>Conservación</h2><p>Por el tiempo necesario para gestionar la consulta y un máximo de 24 meses, salvo obligación legal.</p>
<h2>Tus derechos</h2><p>Podés solicitar acceso, rectificación, actualización o supresión de tus datos escribiendo a {C.EMAIL_CONTACTO}. El titular de los datos personales tiene la facultad de ejercer el derecho de acceso a los mismos en forma gratuita a intervalos no inferiores a seis meses, salvo que se acredite un interés legítimo al efecto conforme lo establecido en el artículo 14, inciso 3 de la Ley N° 25.326. La Agencia de Acceso a la Información Pública, en su carácter de Órgano de Control de la Ley N° 25.326, tiene la atribución de atender las denuncias y reclamos que interpongan quienes resulten afectados en sus derechos por incumplimiento de las normas vigentes en materia de protección de datos personales.</p>""",
    sources=[AAIP],
))

PAGES.append(dict(
    path="/terminos/", kind="page", crumbs=[("Términos", "/terminos/")],
    title="Términos y condiciones", description="Condiciones de uso del sitio y del servicio de diagnóstico.",
    h1="Términos y condiciones",
    body=f"""<p>Última actualización: {C.UPDATED_HUMAN}.</p>
<h2>Contenido informativo</h2><p>La información del sitio es general y no constituye asesoramiento profesional. Para decisiones concretas consultá a un contador público matriculado.</p>
<h2>Herramientas</h2><p>Las calculadoras y tests dan resultados orientativos con base en los datos que ingresás y en la normativa vigente a la fecha indicada.</p>
<h2>Servicio de diagnóstico</h2><p>El diagnóstico es gratuito. El servicio profesional lo presta el estudio aliado, que es el único responsable de su asesoramiento y de sus honorarios.</p>
<h2>Propiedad intelectual</h2><p>Los textos y herramientas son de {C.TITULAR}. Podés citarlos con enlace a la fuente.</p>
<h2>Ley aplicable</h2><p>Estos términos se rigen por las leyes de la República Argentina.</p>""",
))

PAGES.append(dict(
    path="/whatsapp/", kind="page", crumbs=[("Conectar WhatsApp", "/whatsapp/")],
    title="Cómo conectar tu WhatsApp con tu Copiloto Contable de ARCA",
    description="Guía paso a paso para hablarle a tu estudio contable por WhatsApp: emitir facturas, pedir QR de pago y auditar impuestos desde tu chat habitual con Claude o ChatGPT.",
    h1="Conectá tu propio WhatsApp con tu Copiloto de ARCA",
    body=f"""<div class="wrap layout" style="padding-top:20px"><div class="main">
<p class="lead">No necesitás bajarte otra app ni esperar a que un contador te responda de 9 a 18 hs. Podés conectar tu propio WhatsApp con tu IA (Claude o ChatGPT) para manejar más de 80 trámites de ARCA por mensaje de texto o audio.</p>

<div class="answer">
<strong>¿Cómo funciona?</strong>
<p>No usamos un número corporativo donde tus datos pasan por terceros. Vos conectás tu propio número de WhatsApp a tu cuenta de IA (mediante integraciones oficiales o puentes personales). Tu IA habla con nuestro servidor seguro MCP de ARCA y te responde en vivo.</p>
</div>

<h2>¿Qué podés pedirle a tu IA por WhatsApp?</h2>
<ul>
<li><strong>"Mandame el QR para pagar el Monotributo":</strong> Entra a ARCA, liquida intereses si está vencido y te manda el código QR para pagar desde Mercado Pago en 10 segundos.</li>
<li><strong>"Facturale $450.000 a mi cliente":</strong> Valida el CUIT en el padrón, determina si es Factura A, B o C, obtiene el CAE en ARCA y te manda el PDF con código QR reglamentario.</li>
<li><strong>"¿Cuánto IVA nos queda a pagar este mes?":</strong> Cruza las compras y ventas de Mis Comprobantes y te dice la posición exacta de fin de mes.</li>
<li><strong>"Recordame el día 18 pagar la cuota":</strong> Te agenda un recordatorio automático antes de que venza.</li>
</ul>

<h2>Paso a paso para activarlo</h2>
<ol style="padding-left:20px;display:grid;gap:16px;margin:24px 0">
<li><strong>Paso 1 · Activar la Skill o MCP en tu IA:</strong> Conectá el conector oficial <code>https://impuesto.com.ar/mcp/sse</code> en tu Claude Desktop o ChatGPT.</li>
<li><strong>Paso 2 · Vincular tu WhatsApp a tu IA:</strong> Podés usar cualquiera de los conectores populares de WhatsApp para LLMs (como Claude WhatsApp Bridge, integraciones en Make/Zapier o asistentes personales de WhatsApp).</li>
<li><strong>Paso 3 · Empezar a operar:</strong> Enviá un mensaje con tu CUIT y pedile lo que necesites. Tu IA ejecuta el trámite en ARCA y te devuelve la constancia oficial al chat.</li>
</ol>

<p style="margin-top:32px"><a class="btn" href="/mcp">Configurar Conector MCP de ARCA →</a> <a class="btn sec" href="/integraciones/">Ver los 80 trámites en roadmap</a></p>
</div>
<div class="side">
<div class="card" style="border-top:4px solid var(--acc)">
<h3>Estudio Contable Total</h3>
<p style="font-size:14px;color:var(--muted)">Más de 80 trámites cubiertos: Monotributo, Facturación A/B/C/E, Libro IVA Digital, Sueldos F. 931, Ingresos Brutos y Certificaciones Contables.</p>
<ul style="padding-left:18px;font-size:13.5px;color:var(--muted);margin:10px 0;display:grid;gap:6px">
<li>Sin horarios de oficina (24/7)</li>
<li>Tu clave fiscal protegida</li>
<li>Análisis claros y sin jerga contable</li>
</ul>
</div>
</div></div>""",
))

PAGES.append(dict(
    path="/estudios/",
    kind="custom",
    title="Modo Estudio Contable (B2B) — Automatizá tu cartera con Claude y ARCA MCP",
    description="Plataforma B2B para estudios contables en Argentina: gestioná 100+ clientes desde Claude o ChatGPT con flujo Junior → Socio, detector de anomalías, Certificado MiPyME, e-APOC y reportes Marca Blanca.",
    h1="Automatizá tu Estudio Contable desde Claude y ChatGPT",
    body="""
<section class="hero" style="background:linear-gradient(135deg, #0B1626 0%, #132A43 100%);color:#fff;padding:56px 0 48px">
  <div class="wrap" style="max-width:980px">
    <span class="kicker" style="color:#4EFA9D">MODO ESTUDIO CONTABLE · B2B MULTI-CLIENTE</span>
    <h1 style="color:#fff;margin:10px 0 14px;font-size:clamp(30px,4.5vw,44px);line-height:1.12;letter-spacing:-.02em">
      Que cada analista lleve 80 a 100 clientes con Claude, control Junior → Socio y tu Marca Blanca
    </h1>
    <p class="lead" style="color:#C7D6E6;max-width:780px;font-size:18px">
      Conectá tu Clave Fiscal delegada de ARCA al servidor MCP de <strong>impuesto.com.ar</strong>. Tus analistas usan su propio plan de Claude o ChatGPT (costo de IA $0 para tu estudio) mientras nuestros bots ejecutan los 13 servicios críticos de ARCA y el sistema protege tu matrícula con aprobación del Socio antes de presentar.
    </p>
    <div class="cta-row" style="margin-top:24px;display:flex;gap:14px;flex-wrap:wrap">
      <a class="btn" href="/mcp" style="background:#0B6E4F;color:#fff;border:0">Conectar Estudio con MCP →</a>
      <a class="btn sec" href="#como-organizarse" style="background:transparent;color:#fff;border:1px solid #3B5470">Cómo organizarse mes a mes en Claude</a>
    </div>
  </div>
</section>

<section class="wrap sec-pad" style="max-width:980px">
  <span class="kicker">Diseñado por y para Socios de Estudios Contables</span>
  <h2 style="margin-top:6px">Los 6 módulos que resuelven el día a día de una cartera de 50 a 500 clientes</h2>

  <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:18px;margin-top:20px">
    <div class="card" style="border-top:4px solid #0B6E4F">
      <h3>1. Alta Masiva de Cartera</h3>
      <p>Importá tus 50, 150 o 300 CUITs de una sola vez (régimen, jurisdicciones, empleados y analista asignado) sin repetir entrevistas cliente por cliente.</p>
    </div>
    <div class="card" style="border-top:4px solid #0B6E4F">
      <h3>2. Tablero por Terminación de CUIT</h3>
      <p>Semáforo diario consolidado por terminación (0–9) y filtrado por analista: quién ya tiene borrador, quién espera revisión del Socio y qué vence esta semana.</p>
    </div>
    <div class="card" style="border-top:4px solid #DC2626">
      <h3>3. Detector de Anomalías (±30%)</h3>
      <p>Antes de firmar un IVA, IIBB o F. 931, el sistema compara el mes actual contra el historial del cliente y prende alerta roja si el impuesto salta más de 30%.</p>
    </div>
    <div class="card" style="border-top:4px solid #0052CC">
      <h3>4. Flujo Estricto Junior → Socio</h3>
      <p>Ningún junior presenta directo en ARCA. Los borradores quedan en <code>pendiente_revision_socio</code> hasta que el Socio los audita y aprueba en bloque.</p>
    </div>
    <div class="card" style="border-top:4px solid #0B6E4F">
      <h3>5. Marca Blanca 100% de tu Estudio</h3>
      <p>Generá en 1 clic el reporte mensual con gráficos, VEPs y recomendaciones firmado con el nombre y matrícula de tu estudio, listo para WhatsApp o email.</p>
    </div>
    <div class="card" style="border-top:4px solid #0052CC">
      <h3>6. 13 Bots ARCA + MiPyME + e-APOC</h3>
      <p>WSFEv1, Mis Comprobantes, DFE, Monotributo, CCMA, Mis Retenciones, Nuestra Parte, BBPP F. 762, RCEL, Renovación MiPyME F. 1272 y auditoría de proveedores en Base e-APOC.</p>
    </div>
  </div>
</section>

<!-- GUÍA PRÁCTICA DE ORGANIZACIÓN EN CLAUDE Y CHATGPT (CERO CHATS ETERNOS) -->
<section id="como-organizarse" style="background:#F6F9FC;border-top:1px solid #E2E8F0;border-bottom:1px solid #E2E8F0;padding:48px 0">
  <div class="wrap" style="max-width:980px">
    <span class="kicker" style="color:#0B6E4F">Arquitectura de Trabajo Mensual · Cero Pérdida de Contexto</span>
    <h2 style="margin-top:6px">¿Cómo usar Claude o ChatGPT todos los meses sin que los chats se vuelvan eternos?</h2>
    <p style="color:var(--muted);font-size:16px;max-width:780px">
      El error más común al usar IA en contabilidad es trabajar durante meses en un solo chat interminable: el contexto se llena, la IA se vuelve lenta y mezcla períodos. <strong>Con nuestro MCP la memoria NO vive en el chat — vive en tu base de datos D1.</strong>
    </p>

    <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:22px;margin-top:24px">
      <div class="card" style="background:#fff;border:1px solid #D5E0EB">
        <div style="color:#0B6E4F;font-weight:800;font-size:13px;margin-bottom:6px">SI SOS 1 EMPRESA O MONOTRIBUTISTA</div>
        <h3 style="margin:0 0 10px">1 Proyecto + 1 Chat limpio por mes</h3>
        <ul style="padding-left:18px;margin:0;display:grid;gap:8px;font-size:14.5px;color:var(--ink)">
          <li>Creás <strong>1 solo Proyecto</strong> en Claude (o Carpeta en ChatGPT) llamado <em>"Impuestos – Mi Empresa"</em> con nuestra Skill y el MCP conectados.</li>
          <li>Cada mes abrís un <strong>chat nuevo y limpio</strong> (ej. <em>"Cierre Noviembre 2026"</em>, <em>"Cierre Diciembre 2026"</em>).</li>
          <li>Al empezar, escribís: <em>"Arranquemos el cierre de diciembre"</em>. Claude consulta tu perfil y tu histórico en D1 en 2 segundos, sin arrastrar cientos de mensajes viejos.</li>
        </ul>
      </div>

      <div class="card" style="background:#fff;border:1px solid #D5E0EB">
        <div style="color:#0052CC;font-weight:800;font-size:13px;margin-bottom:6px">SI SOS UN ESTUDIO CONTABLE (50–300 CLIENTES)</div>
        <h3 style="margin:0 0 10px">NO crees 100 carpetas: 1 Proyecto por Analista</h3>
        <ul style="padding-left:18px;margin:0;display:grid;gap:8px;font-size:14.5px;color:var(--ink)">
          <li>Creás <strong>1 Proyecto por Analista o Equipo</strong> (ej. <em>"Estudio Rivera – Cartera Sofía"</em>) conectado al mismo <code>estudio_id</code>.</li>
          <li>Abrís <strong>1 chat nuevo por tarea o cierre puntual</strong> (ej. <em>"Barrido DFE Lunes 25/11"</em>, <em>"Cierre IVA Nov – Innovatech"</em>, <em>"Revisión Socio Viernes"</em>).</li>
          <li>Cada borrador, anomalía y aprobación queda guardada en D1 por <code>estudio_id + cuit + período</code>. Cuando el Socio abre su chat a las 18 hs, ve al instante todo lo que preparó el equipo.</li>
        </ul>
      </div>
    </div>

    <div style="margin-top:22px;background:#0F1B2D;color:#fff;border-radius:12px;padding:20px 24px;display:flex;flex-wrap:wrap;gap:16px;align-items:center;justify-content:space-between">
      <div style="flex:1 1 520px">
        <strong style="color:#4EFA9D;font-size:15px">⚡ Regla de oro para un chat siempre rápido y preciso:</strong>
        <p style="margin:6px 0 0;color:#CBD5E1;font-size:14px">
          Chat nuevo para cada cierre mensual o lote de trabajo. Tu perfil fiscal, tu cartera de clientes, tus desvíos históricos y los criterios resueltos por especialistas siempre viajan automáticamente desde el servidor MCP.
        </p>
      </div>
      <a class="btn" href="/mcp" style="background:#0B6E4F;color:#fff;border:0">Activar en mi Estudio →</a>
    </div>
  </div>
</section>
""",
))

PAGES.append(dict(
    path="/404/", kind="custom", noindex=True, title="Página no encontrada", description="La página no existe.", h1="Página no encontrada",
    body="""<div class="wrap" style="max-width:760px;padding:56px 20px 80px"><h1>No encontramos esta página</h1>
<p class="lead">Puede que se haya movido. Probá con:</p>
<ul><li><a href="/monotributo/categorias/">Categorías del monotributo</a></li><li><a href="/empresas/">Impuestos para empresas</a></li><li><a href="/diagnostico/">Diagnóstico gratis</a></li></ul></div>""",
))
