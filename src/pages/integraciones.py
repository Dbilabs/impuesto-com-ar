"""Página de Roadmap y Votación de Integraciones ARCA con IA."""

PAGES = []

VOTING_FEATURES = [
    {
        "id": "ddjj",
        "badge": "En desarrollo",
        "badge_color": "#D97706",
        "badge_bg": "#FEF3C7",
        "title": "Presentación de Declaraciones Juradas y Pagos (F. 2002 / VEP)",
        "desc": "Armado automático del borrador de la declaración jurada mensual de IVA por actividad, presentación oficial con confirmación de tu IA y generación del VEP para pagar en el homebanking.",
        "votes": 142
    },
    {
        "id": "rectificativas",
        "badge": "En votación",
        "badge_color": "#0B6E4F",
        "badge_bg": "#E7F3EE",
        "title": "Rectificativas de Declaraciones Juradas",
        "desc": "Detección automática de discrepancias u omisiones entre libros contables y ARCA, con generación y presentación asistida de declaraciones juradas rectificativas sin errores.",
        "votes": 118
    },
    {
        "id": "portal-iva",
        "badge": "En votación",
        "badge_color": "#0B6E4F",
        "badge_bg": "#E7F3EE",
        "title": "Libro de IVA Digital (Portal IVA)",
        "desc": "Importación sin errores de alícuotas para compras y ventas, prorrateo de crédito fiscal computable y confirmación del cierre mensual oficial obligatorio.",
        "votes": 95
    },
    {
        "id": "facturacion",
        "badge": "En desarrollo",
        "badge_color": "#D97706",
        "badge_bg": "#FEF3C7",
        "title": "Emisión de Facturas y Notas de Crédito (RCEL / WSFE)",
        "desc": "Emitir facturas A, B o C directamente dictándole a Claude o ChatGPT los datos del cliente, concepto y monto, obteniendo el CAE oficial al instante.",
        "votes": 89
    },
    {
        "id": "retenciones",
        "badge": "En votación",
        "badge_color": "#0B6E4F",
        "badge_bg": "#E7F3EE",
        "title": "Mis Retenciones (SICORE / SIRE / Bancarias)",
        "desc": "Descarga consolidada de retenciones y percepciones sufridas de IVA y Ganancias en bancos y grandes empresas para cómputo directo en tus liquidaciones.",
        "votes": 76
    },
    {
        "id": "cuentas-tributarias",
        "badge": "En votación",
        "badge_color": "#0B6E4F",
        "badge_bg": "#E7F3EE",
        "title": "Sistema de Cuentas Tributarias (Saldos a Favor)",
        "desc": "Consulta en tiempo real de saldos a favor de libre disponibilidad, compensación automática de impuestos cruzados y estado de cuenta corriente.",
        "votes": 64
    },
    {
        "id": "monotributo",
        "badge": "En votación",
        "badge_color": "#0B6E4F",
        "badge_bg": "#E7F3EE",
        "title": "Monotributo y Recategorización Preventiva",
        "desc": "Monitoreo continuo de la facturación acumulada últimos 12 meses, alertas tempranas antes de superar los límites de exclusión y simulación de recategorización.",
        "votes": 58
    },
    {
        "id": "sueldos",
        "badge": "En votación",
        "badge_color": "#0B6E4F",
        "badge_bg": "#E7F3EE",
        "title": "Libro de Sueldos Digital (F. 931)",
        "desc": "Validación de liquidaciones de sueldos, carga de novedades de nómina y presentación de aportes y contribuciones a la seguridad social.",
        "votes": 41
    },
    {
        "id": "percepciones",
        "badge": "En votación",
        "badge_color": "#0B6E4F",
        "badge_bg": "#E7F3EE",
        "title": "Devolución de Percepciones (F. 1746)",
        "desc": "Trámite masivo de solicitud de devolución del 30% / 35% de percepciones por compra de moneda extranjera o consumos con tarjeta en el exterior.",
        "votes": 37
    }
]

def render_cards():
    html = []
    for f in VOTING_FEATURES:
        html.append(f'''
<div class="card vote-card" data-id="{f['id']}" style="display:flex;flex-direction:column;justify-content:space-between">
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <span style="background:{f['badge_bg']};color:{f['badge_color']};font-size:12px;font-weight:700;padding:3px 8px;border-radius:6px">{f['badge']}</span>
      <span class="vote-count-wrap" style="color:var(--muted);font-size:14px;font-weight:600"><span class="vote-num" id="count-{f['id']}">{f['votes']}</span> votos</span>
    </div>
    <h3 style="margin:0 0 10px;font-size:19px;line-height:1.3">{f['title']}</h3>
    <p style="margin:0;color:var(--muted);font-size:15px;line-height:1.5">{f['desc']}</p>
  </div>
  <div style="margin-top:20px;padding-top:14px;border-top:1px solid var(--line);display:flex;justify-content:space-between;align-items:center">
    <button type="button" class="btn sec sm btn-vote" data-id="{f['id']}" style="width:100%;font-size:14px;gap:6px">
      <span class="vote-icon">▲</span> <span class="vote-text">Votar esta integración</span>
    </button>
  </div>
</div>
''')
    return "".join(html)

BODY = f'''
<section class="wrap sec-pad" style="padding-top:32px;padding-bottom:32px">
  <div style="background:var(--tint);border:1px solid #C4E2D5;border-radius:14px;padding:24px 28px;margin-bottom:36px;display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:20px">
    <div style="flex:1 1 480px;min-width:0">
      <span class="pill" style="margin-bottom:8px">Conector MCP ya disponible</span>
      <h2 style="margin:4px 0 8px;font-size:22px">Conectá ARCA a Claude y ChatGPT hoy mismo</h2>
      <p style="margin:0;color:var(--muted);font-size:16px">Ya podés consultar comprobantes emitidos y recibidos, estimar tu IVA mensual y leer notificaciones del Domicilio Fiscal Electrónico desde tu IA sin instalar nada.</p>
    </div>
    <div>
      <a class="btn" href="/mcp/" style="white-space:nowrap">Conectar conector MCP →</a>
    </div>
  </div>

  <span class="kicker">Roadmap colaborativo · ARCA + Inteligencia Artificial</span>
  <h2 style="margin:8px 0 12px;font-size:clamp(26px,4vw,36px)">Votá qué otras integraciones te gustaría tener</h2>
  <p class="lead" style="max-width:800px;margin-bottom:32px">
    Queremos que tu asistente de IA resuelva la mayor cantidad de trámites fiscales posibles. Elegí las funcionalidades que más tiempo te ahorrarían en el día a día para priorizar su lanzamiento.
  </p>

  <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px">
    {render_cards()}
  </div>

  <!-- Formulario de sugerencia -->
  <div class="card" style="margin-top:40px;padding:32px;background:#fff;border:1px solid var(--line)">
    <span class="kicker">¿Falta algún trámite o sistema?</span>
    <h3 style="margin:6px 0 10px;font-size:22px">Sugerí qué otra integración te gustaría ver</h3>
    <p style="color:var(--muted);margin:0 0 20px;font-size:16px">Si usás otros organismos provinciales (ARBA, AGIP, SIFERE), bancos o necesitás un trámite específico de ARCA que no esté en la lista, contanos acá:</p>
    
    <form id="form-sugerencia" style="max-width:680px">
      <label for="f-sugerencia">¿Qué trámite, impuesto o sistema necesitás integrar?</label>
      <textarea id="f-sugerencia" name="sugerencia" required maxlength="500" placeholder="Ej.: Integración con ARBA para consultar padrón de retenciones, o presentación de CITI Compras..." style="height:90px"></textarea>
      
      <div class="row2" style="margin-top:12px">
        <div>
          <label for="f-email-sug">Tu email (opcional, para avisarte cuando esté lista)</label>
          <input id="f-email-sug" type="email" name="email" placeholder="vos@tuempresa.com">
        </div>
        <div style="display:flex;align-items:flex-end">
          <button class="btn" type="submit" style="width:100%;min-height:46px">Enviar sugerencia</button>
        </div>
      </div>
      <p id="msg-sugerencia" style="margin:14px 0 0;font-weight:600;display:none"></p>
    </form>
  </div>
</section>

<script>
(function() {{
  var votesKey = "impuesto_votos_arca";
  var myVotes = JSON.parse(localStorage.getItem(votesKey) || "[]");

  // Actualizar conteos desde la API
  fetch("/api/votar")
    .then(function(r) {{ return r.json(); }})
    .then(function(data) {{
      if (data && data.counts) {{
        for (var k in data.counts) {{
          var el = document.getElementById("count-" + k);
          if (el) el.innerText = data.counts[k];
        }}
      }}
    }}).catch(function() {{}});

  // Marcar los ya votados en este navegador
  function updateButtons() {{
    document.querySelectorAll(".btn-vote").forEach(function(btn) {{
      var id = btn.getAttribute("data-id");
      if (myVotes.indexOf(id) > -1) {{
        btn.classList.remove("sec");
        btn.style.background = "#E7F3EE";
        btn.style.color = "#0B6E4F";
        btn.style.borderColor = "#0B6E4F";
        btn.innerHTML = '<span>✓</span> <span>Votado</span>';
      }}
    }});
  }}
  updateButtons();

  // Click en votar
  document.querySelectorAll(".btn-vote").forEach(function(btn) {{
    btn.addEventListener("click", function() {{
      var id = btn.getAttribute("data-id");
      if (myVotes.indexOf(id) > -1) return; // ya votó

      myVotes.push(id);
      localStorage.setItem(votesKey, JSON.stringify(myVotes));
      
      var el = document.getElementById("count-" + id);
      if (el) el.innerText = parseInt(el.innerText || "0", 10) + 1;

      updateButtons();

      fetch("/api/votar", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ feature_id: id }})
      }}).catch(function() {{}});
    }});
  }});

  // Formulario de sugerencia
  var form = document.getElementById("form-sugerencia");
  var msg = document.getElementById("msg-sugerencia");
  if (form) {{
    form.addEventListener("submit", function(e) {{
      e.preventDefault();
      var sug = document.getElementById("f-sugerencia").value;
      var email = document.getElementById("f-email-sug").value;
      
      fetch("/api/votar", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ feature_id: "sugerencia_nueva", sugerencia: sug, email: email }})
      }}).then(function() {{
        form.reset();
        msg.style.display = "block";
        msg.style.color = "#0B6E4F";
        msg.innerText = "¡Muchas gracias! Registramos tu sugerencia y la sumamos a la lista de prioridades.";
      }}).catch(function() {{
        msg.style.display = "block";
        msg.style.color = "#B91C1C";
        msg.innerText = "Hubo un error al enviar. Por favor probá de nuevo.";
      }});
    }});
  }}
}})();
</script>
'''

PAGES.append(dict(
    path="/integraciones/", kind="custom", crumbs=[("Integraciones ARCA", "/integraciones/")],
    title="Integraciones ARCA con IA: Roadmap y Votación",
    description="Votá qué integraciones de ARCA (AFIP) te gustaría conectar con Claude, ChatGPT o sistemas contables: presentaciones de DDJJ, rectificativas, Libro IVA Digital y más.",
    h1="Votá las próximas integraciones oficiales con ARCA",
    body=BODY
))
