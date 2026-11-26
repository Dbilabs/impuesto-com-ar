(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var ars = function (n) { return "$\u00a0" + Math.round(n).toLocaleString("es-AR"); };
  var params = new URLSearchParams(location.search);

  // Guarda el origen del visitante (UTM, referrer, landing) para atribuir cada lead.
  try {
    if (!sessionStorage.getItem("orig")) {
      var o = { landing: location.pathname, referrer: document.referrer || "" };
      ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid"].forEach(function (k) { if (params.get(k)) o[k] = params.get(k); });
      sessionStorage.setItem("orig", JSON.stringify(o));
    }
  } catch (e) {}
  function origin() { try { return JSON.parse(sessionStorage.getItem("orig") || "{}"); } catch (e) { return {}; } }

  // ---------- Diagnóstico (embudo de leads) ----------
  var TEMAS = {
    ri: [
      ["iva-planificacion", "Planificar el IVA del mes", "Saber cuánto viene y cómo bajarlo"],
      ["iva-automatico", "Quiero el cálculo automático del IVA", "Aviso semanal sin compartir mi clave fiscal"],
      ["ganancias-bienes", "Ganancias o Bienes Personales", "Anticipos, deducciones, declaración jurada"],
      ["saldos-a-favor", "Tengo saldos a favor que no puedo usar", "Retenciones y percepciones de IVA o IIBB"],
      ["cambiar-contador", "Cambiar de contador o cotizar uno", ""],
      ["otro", "Otra consulta", ""]
    ],
    persona: [
      ["monotributo-categoria", "Revisar mi categoría de monotributo", "¿Estoy pagando de más o de menos?"],
      ["cambiar-contador", "Cambiar de contador o cotizar uno", "Quiero saber cuánto cuesta y qué incluye"],
      ["exclusion", "Me excluyeron o temo que me excluyan", "Intimaciones, recategorización de oficio"],
      ["inscripcion", "Inscribirme, pasar a responsable inscripto o darme de baja", ""],
      ["ganancias-bienes", "Ganancias o Bienes Personales", "Declaraciones juradas, deducciones"],
      ["otro", "Otra consulta", ""]
    ],
    empresa: [
      ["saldos-a-favor", "Recuperar saldos a favor", "Retenciones y percepciones de IIBB, IVA"],
      ["auditoria", "Auditoría de estados contables", "Balance auditado para IGJ, banco, licitación o casa matriz"],
      ["fiscalizacion", "Fiscalización o requerimiento de ARCA", "Prevenir o responder"],
      ["planificacion", "Planificación fiscal", "Pagar lo que corresponde, no más"],
      ["convenio-multilateral", "Convenio Multilateral / Ingresos Brutos", "Operación en varias provincias"],
      ["precios-transferencia", "Precios de transferencia", "Operaciones con vinculadas del exterior"],
      ["cambiar-estudio", "Cambiar de estudio contable", "Comparar propuestas"],
      ["otro", "Otra consulta", ""]
    ]
  };
  var SITUACION = {
    ri: ["Facturo hasta $100 millones por año", "Entre $100 y $500 millones por año", "Más de $500 millones por año", "Recién paso del monotributo"],
    persona: ["Soy monotributista", "Soy responsable inscripto / autónomo", "Trabajo en relación de dependencia", "Todavía no estoy inscripto"],
    empresa: ["1 a 10 empleados", "11 a 50 empleados", "51 a 200 empleados", "Más de 200 empleados"]
  };

  function initDiag(root) {
    var st = { step: 1, perfil: null, tema: null, situacion: null };
    var pre = params.get("perfil"), preT = params.get("tema");
    if (pre === "persona" || pre === "empresa" || pre === "ri") { st.perfil = pre; st.step = 2; }
    if (st.perfil && preT && TEMAS[st.perfil].some(function (t) { return t[0] === preT; })) { st.tema = preT; st.step = 3; }
    var title = $(".d-title", root), body = $(".d-body", root), bar = $(".bar i", root), num = $(".d-num", root), back = $(".d-back", root);

    function optBtn(label, sub, onclick) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "opt";
      b.innerHTML = "<span>" + label + (sub ? "<small>" + sub + "</small>" : "") + "</span>";
      b.addEventListener("click", onclick);
      return b;
    }
    function render() {
      bar.style.width = (Math.min(st.step, 4) * 25) + "%";
      num.textContent = "Paso " + Math.min(st.step, 4) + " de 4";
      back.hidden = st.step === 1;
      body.innerHTML = "";
      var wrap = document.createElement("div"); wrap.className = "opts";
      if (st.step === 1) {
        title.textContent = "¿Para quién es la consulta?";
        wrap.appendChild(optBtn("Para mi empresa", "Impuestos y auditoría para pymes y empresas medianas", function () { st.perfil = "empresa"; st.step = 2; render(); }));
        wrap.appendChild(optBtn("Soy responsable inscripto o profesional", "IVA, Ganancias, autónomos, Ingresos Brutos", function () { st.perfil = "ri"; st.step = 2; render(); }));
        wrap.appendChild(optBtn("Soy monotributista", "Categoría, recategorización, pase a responsable inscripto", function () { st.perfil = "persona"; st.step = 2; render(); }));
      } else if (st.step === 2) {
        title.textContent = "¿Qué querés resolver?";
        TEMAS[st.perfil].forEach(function (t) { wrap.appendChild(optBtn(t[1], t[2], function () { st.tema = t[0]; st.step = 3; render(); })); });
      } else if (st.step === 3) {
        title.textContent = st.perfil === "empresa" ? "¿Cuántas personas trabajan en la empresa?" : st.perfil === "ri" ? "¿Cuánto facturás aproximadamente?" : "¿Cuál es tu situación hoy?";
        SITUACION[st.perfil].forEach(function (s) { wrap.appendChild(optBtn(s, "", function () { st.situacion = s; st.step = 4; render(); })); });
      } else {
        title.textContent = "¿A dónde te enviamos el diagnóstico?";
        var tpl = $("#tpl-form-" + (st.perfil === "empresa" ? "empresa" : "persona"));
        body.appendChild(tpl.content.cloneNode(true));
        bindForm($("form", body));
        return;
      }
      body.appendChild(wrap);
      var first = $("button", wrap); if (first && st.step > 1) first.focus({ preventScroll: true });
    }
    function bindForm(f) {
      f.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var err = $(".err", f); err.textContent = "";
        if (!f.reportValidity()) return;
        var data = {};
        new FormData(f).forEach(function (v, k) { data[k] = String(v).trim(); });
        var payload = Object.assign({}, data, { perfil: st.perfil, tema: st.tema, situacion: st.situacion, pagina: location.pathname }, origin());
        var btn = $("button[type=submit]", f); btn.disabled = true; btn.textContent = "Enviando…";
        fetch("/api/lead", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })
          .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok || !j.ok) throw new Error(j.error || "error"); return j; }); })
          .then(function () { location.href = "/gracias/?perfil=" + encodeURIComponent(st.perfil); })
          .catch(function () { btn.disabled = false; btn.textContent = "Quiero mi diagnóstico gratis"; err.textContent = "No pudimos enviar tu consulta. Probá de nuevo en un minuto o escribinos a " + (root.dataset.email || "nuestro correo") + "."; });
      });
    }
    back.addEventListener("click", function () { st.step = Math.max(1, st.step - 1); render(); });
    render();
  }
  $$("[data-diag]").forEach(initDiag);

  // ---------- Calculadora de monotributo ----------
  var monoEl = $("#mono-data");
  var MONO = monoEl ? JSON.parse(monoEl.textContent) : null;
  var calc = $("#calc-mono");
  if (calc && MONO) {
    calc.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var ing = parseFloat(String($("#ingresos", calc).value).replace(/\./g, "").replace(",", "."));
      var tipo = $("#tipo", calc).value, actual = $("#actual", calc).value;
      var out = $(".result", calc); out.hidden = false;
      if (!(ing >= 0)) { out.innerHTML = "<p>Ingresá tu facturación de los últimos 12 meses.</p>"; return; }
      var cats = MONO.categorias, c = null;
      for (var i = 0; i < cats.length; i++) { if (ing <= cats[i].tope) { c = cats[i]; break; } }
      if (!c) {
        out.innerHTML = "<p class='big'>Superás la categoría K</p><p>Con " + ars(ing) + " en 12 meses superás el tope máximo del monotributo (" + ars(cats[cats.length - 1].tope) + "). Es una causal de exclusión: conviene que lo revise un contador cuanto antes.</p><a class='btn' href='/diagnostico/?perfil=persona&tema=exclusion'>Hablar con un contador</a>";
        return;
      }
      var cuota = c[tipo], margen = c.tope - ing, html = "<p style='margin:0'>Por ingresos te corresponde la</p><p class='big' style='margin:0'>Categoría " + c.cat + "</p><p>Cuota mensual (" + (tipo === "servicios" ? "servicios" : "venta de bienes") + "): <strong>" + ars(cuota) + "</strong>. Te quedan " + ars(margen) + " de margen hasta el tope de la categoría.</p>";
      if (actual) {
        var a = cats.filter(function (x) { return x.cat === actual; })[0];
        if (a && a[tipo] > cuota) html += "<p><strong>Podrías estar pagando de más:</strong> hoy pagás " + ars(a[tipo]) + " por mes en la " + a.cat + ". La diferencia es de " + ars((a[tipo] - cuota) * 12) + " por año.</p>";
        else if (a && a[tipo] < cuota) html += "<p><strong>Atención:</strong> estás en la " + a.cat + " pero por ingresos te corresponde la " + c.cat + ". Si no te recategorizás, ARCA puede hacerlo de oficio y aplicar sanciones.</p>";
        else if (a) html += "<p>Tu categoría actual coincide con tus ingresos.</p>";
      }
      html += "<p style='font-size:14px'>Además de los ingresos, la categoría depende de la superficie, la energía consumida y los alquileres. Un contador lo verifica sin pedirte la clave fiscal.</p><a class='btn' href='/diagnostico/?perfil=persona&tema=monotributo-categoria'>Que un contador revise mi caso</a>";
      out.innerHTML = html;
    });
  }

  // ---------- Cuestionarios Sí/No con puntaje ----------
  $$("[data-quiz]").forEach(function (q) {
    var answers = {};
    var levels = JSON.parse(q.getAttribute("data-levels"));
    var rows = $$(".qrow", q);
    rows.forEach(function (row, i) {
      $$(".yn button", row).forEach(function (b) {
        b.addEventListener("click", function () {
          answers[i] = b.dataset.v === (q.hasAttribute("data-invert") ? "0" : "1") ? parseFloat(row.dataset.w || "1") : 0;
          $$(".yn button", row).forEach(function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); x.className = "btn sm " + (x === b ? "" : "sec"); });
        });
      });
    });
    $(".q-go", q).addEventListener("click", function () {
      var out = $(".result", q); out.hidden = false;
      if (Object.keys(answers).length < rows.length) { out.innerHTML = "<p>Respondé todas las preguntas para ver tu resultado (" + Object.keys(answers).length + " de " + rows.length + ").</p>"; return; }
      var pts = Object.keys(answers).reduce(function (s, k) { return s + answers[k]; }, 0), lv = levels[0];
      levels.forEach(function (l) { if (pts >= l.min) lv = l; });
      out.innerHTML = "<p class='big' style='margin:0'>" + lv.title + "</p><p>" + lv.text + "</p><a class='btn' href='" + q.dataset.cta + "'>" + (q.dataset.ctaLabel || "Hablar con un especialista") + "</a>";
    });
  });

  // ---------- Estimador de saldos a favor ----------
  var sal = $("#calc-saldos");
  if (sal) {
    sal.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var n = function (id) { return parseFloat(String($(id, sal).value || "0").replace(/\./g, "").replace(",", ".")) || 0; };
      var ret = n("#ret"), det = n("#det"), acum = n("#acum");
      var mensual = ret - det, anual = acum + Math.max(mensual, 0) * 12;
      var out = $(".result", sal); out.hidden = false;
      if (mensual <= 0 && acum <= 0) { out.innerHTML = "<p>Con estos números no se acumula saldo a favor: las retenciones y percepciones no superan el impuesto. Igual vale revisar alícuotas y regímenes aplicados.</p>"; return; }
      out.innerHTML = "<p style='margin:0'>Saldo a favor estimado dentro de 12 meses</p><p class='big' style='margin:0'>" + ars(anual) + "</p><p>" + (mensual > 0 ? "Cada mes se acumulan unos " + ars(mensual) + " que la empresa no puede usar. " : "") + "Es capital de trabajo inmovilizado. Según la jurisdicción, se puede pedir reducción o exclusión de regímenes, compensar o solicitar la devolución.</p><a class='btn' href='/diagnostico/?perfil=empresa&tema=saldos-a-favor'>Quiero un plan de recupero</a>";
    });
  }


  // ---------- Convenio Multilateral: coeficientes ----------
  var cm = $("#calc-cm");
  if (cm) {
    var nn = function (v) { var s = String(v || "").replace(/\s|\$/g, ""); if (s.indexOf(",") > -1 || /^-?\d{1,3}(\.\d{3})+$/.test(s)) s = s.replace(/\./g, "").replace(",", "."); return parseFloat(s) || 0; };
    var rowsEl = $("#cm-rows", cm);
    var addRow = function (prov) { var n = $("#cm-row").content.cloneNode(true); if (prov) $(".cm-prov", n).value = prov; rowsEl.appendChild(n); };
    var calcCM = function () {
      var rs = $$(".cm-row", rowsEl), I = 0, G = 0, data = [];
      rs.forEach(function (r) { var d = { p: $(".cm-prov", r).value, i: nn($(".cm-ing", r).value), g: nn($(".cm-gas", r).value) }; I += d.i; G += d.g; data.push(d); });
      var out = $("#cm-out", cm);
      if (!I || !G) { out.hidden = true; return; }
      var base = nn($("#cm-base", cm).value), acc = {};
      data.forEach(function (d) { var c = 0.5 * d.i / I + 0.5 * d.g / G; acc[d.p] = (acc[d.p] || 0) + c; });
      var rows = Object.keys(acc).sort(function (a, b) { return acc[b] - acc[a]; }).map(function (p) {
        return "<tr><td>" + p + "</td><td class='num'>" + (acc[p] * 100).toFixed(4).replace(".", ",") + "%</td>" + (base ? "<td class='num'>" + ars(base * acc[p]) + "</td>" : "") + "</tr>";
      }).join("");
      out.hidden = false;
      out.innerHTML = "<div class='tbl' style='margin:0'><table><thead><tr><th>Provincia</th><th class='num'>Coeficiente unificado</th>" + (base ? "<th class='num'>Base imponible asignada</th>" : "") + "</tr></thead><tbody>" + rows + "</tbody></table></div>" +
        "<p class='src'>Régimen general (art. 2). Los regímenes especiales usan otras reglas. Los gastos y los ingresos computables tienen criterios específicos: conviene validarlos.</p><a class='btn' href='/diagnostico/?perfil=empresa&tema=convenio-multilateral'>Revisar mis coeficientes con un especialista</a>";
    };
    $("#cm-add", cm).addEventListener("click", function () { addRow(); });
    rowsEl.addEventListener("click", function (e) { if (e.target.classList.contains("cm-del")) { e.target.closest(".cm-row").remove(); calcCM(); } });
    cm.addEventListener("input", calcCM); cm.addEventListener("change", calcCM);
    addRow("Ciudad Autónoma de Buenos Aires"); addRow("Buenos Aires");
  }

  // ---------- Anticipos de Ganancias ----------
  var an = $("#calc-anticipos");
  if (an) {
    an.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var nn = function (id) { var s = String($(id, an).value || "").replace(/\s|\$/g, ""); if (s.indexOf(",") > -1 || /^-?\d{1,3}(\.\d{3})+$/.test(s)) s = s.replace(/\./g, "").replace(",", "."); return parseFloat(s) || 0; };
      var base = nn("#an-base"), est = nn("#an-est"), pag = nn("#an-pag"), out = $(".result", an); out.hidden = false;
      if (!base) { out.innerHTML = "<p>Ingresá el impuesto determinado del ejercicio anterior.</p>"; return; }
      var exceso = base - est;
      if (exceso <= 0) { out.innerHTML = "<p>Con estos números los anticipos no superan el impuesto estimado: no aparece un exceso para reducir.</p>"; return; }
      var pend = Math.max(base - pag, 0), libera = Math.min(exceso, pend), pct = est > 0 ? (exceso / est * 100) : 100;
      out.innerHTML = "<p style='margin:0'>Anticipos por encima del impuesto estimado</p><p class='big' style='margin:0'>" + ars(exceso) + "</p>" +
        "<p>Los anticipos superan tu estimación en un <strong>" + Math.round(pct) + "%</strong>. " + (pag ? "De lo que falta pagar este ejercicio, una reducción podría liberar hasta <strong>" + ars(libera) + "</strong> de caja." : "Una reducción podría liberar esa caja durante el ejercicio.") + "</p>" +
        "<p class='src'>La reducción se pide en ARCA cuando el exceso supera los porcentajes que fija la normativa. Si al final el impuesto resulta mayor, se pagan intereses: conviene una proyección seria.</p>" +
        "<a class='btn' href='/diagnostico/?perfil=empresa&tema=planificacion'>Quiero evaluar la reducción</a>";
    });
  }

  // ---------- Copiar plantilla ----------
  $$("[data-copy]").forEach(function (b) {
    b.addEventListener("click", function () {
      var t = $(b.dataset.copy).innerText;
      navigator.clipboard.writeText(t).then(function () { b.textContent = "¡Copiado!"; }).catch(function () { b.textContent = "Seleccioná el texto y copialo"; });
    });
  });
})();
