// IVA automático: conexión del CUIT (/iva/) y panel privado (/iva/mi-cuenta/).
(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var ars = function (n) { return "$ " + Math.round(n || 0).toLocaleString("es-AR"); };
  var num = function (v) { var s = String(v || "").replace(/\s|\$/g, ""); if (s.indexOf(",") > -1 || /^-?\d{1,3}(\.\d{3})+$/.test(s)) s = s.replace(/\./g, "").replace(",", "."); return parseFloat(s) || 0; };
  var MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
  var nombreMes = function (p) { var a = p.split("-"); return MESES[+a[1] - 1] + " " + a[0]; };
  var KEY = "iva_token";
  var store = { get: function () { try { return localStorage.getItem(KEY); } catch (e) { return null; } }, set: function (t) { try { localStorage.setItem(KEY, t); } catch (e) {} }, del: function () { try { localStorage.removeItem(KEY); } catch (e) {} } };
  function api(path, body) {
    return fetch("/api/iva/" + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().catch(function () { return { ok: false, error: "Error de conexión" }; }).then(function (j) { j.status = r.status; return j; }); });
  }
  function periodoOffset(k) { var d = new Date(Date.now() - 3 * 3600e3); d.setUTCDate(1); d.setUTCMonth(d.getUTCMonth() - k); return d.getUTCFullYear() + "-" + String(d.getUTCMonth() + 1).padStart(2, "0"); }

  // Espera a que el robot termine (consulta cada 5 s, hasta 5 min).
  function esperar(token, consulta, onTick) {
    var t0 = Date.now();
    return new Promise(function (ok, ko) {
      (function loop() {
        api("estado", { token: token, consulta: consulta }).then(function (j) {
          if (!j.ok) return ko(new Error(j.error));
          var c = j.consulta;
          if (c && c.estado === "lista") return ok(j);
          if (c && c.estado === "error") return ko(new Error(c.error));
          if (Date.now() - t0 > 300000) return ko(new Error("ARCA está demorando. Volvé a tu panel en unos minutos."));
          onTick && onTick(Math.round((Date.now() - t0) / 1000));
          setTimeout(loop, 5000);
        }).catch(ko);
      })();
    });
  }

  // Resultado con ajuste manual de retenciones y saldo técnico.
  function renderResultado(el, r) {
    el.innerHTML =
      "<p class='src' style='margin:0'>IVA de " + nombreMes(r.periodo) + " · " + r.n_emitidos + " comprobantes emitidos y " + r.n_recibidos + " recibidos · consultado en ARCA el " + new Date(r.calculado).toLocaleString("es-AR") + "</p>" +
      "<div class='grid' style='gap:12px;margin-top:10px'>" +
      "<div><span class='src'>Débito fiscal (ventas)</span><div style='font-weight:700;font-size:20px'>" + ars(r.debito) + "</div></div>" +
      "<div><span class='src'>Crédito fiscal (compras)</span><div style='font-weight:700;font-size:20px'>" + ars(r.credito) + "</div></div></div>" +
      "<div class='row2'><div><label>Retenciones y percepciones de IVA del mes</label><input type='text' inputmode='numeric' class='aj-ret' placeholder='0'></div>" +
      "<div><label>Saldo técnico / libre disponibilidad anterior</label><input type='text' inputmode='numeric' class='aj-st' placeholder='0'></div></div>" +
      "<div class='aj-out' aria-live='polite'></div>";
    var upd = function () {
      var ret = num($(".aj-ret", el).value), st = num($(".aj-st", el).value);
      var det = r.debito - r.credito - st, pagar = Math.max(det, 0) - ret, out = $(".aj-out", el), h;
      if (pagar > 0) {
        h = "<p style='margin:14px 0 0'>IVA estimado a pagar</p><p class='big' style='margin:0'>" + ars(pagar) + "</p>" +
          "<p><strong>Para planificar:</strong> compras gravadas al 21% por unos <strong>" + ars(pagar / 0.21) + " + IVA</strong>, facturadas a tu CUIT dentro de este mes, llevarían el saldo a cero. Adelantar compras no ahorra impuesto: conviene si la compra la ibas a hacer igual.</p>";
      } else {
        h = "<p style='margin:14px 0 0'>Este mes no pagarías IVA</p><p class='big' style='margin:0'>" + ars(0) + "</p><p>Saldo a favor estimado: <strong>" + ars(-pagar) + "</strong>.</p>";
      }
      if (r.top_proveedores && r.top_proveedores.length) h += "<details><summary style='cursor:pointer;font-weight:600'>Proveedores con más crédito fiscal</summary><ul>" + r.top_proveedores.map(function (p) { return "<li>" + p.nombre.replace(/</g, "&lt;") + ": " + ars(p.iva) + "</li>"; }).join("") + "</ul></details>";
      h += "<p class='src'>No incluye retenciones ni percepciones salvo que las cargues arriba. Es una estimación: la declaración jurada la confirma tu contador en IVA Simple.</p>" +
        "<a class='btn' href='/diagnostico/?perfil=ri&amp;tema=iva-planificacion'>Que un especialista planifique mi IVA</a>";
      out.innerHTML = h;
    };
    el.addEventListener("input", upd); upd();
  }

  // ---------- Conectar (/iva/) ----------
  var form = $("#iva-conectar");
  if (form) {
    var prev = store.get();
    if (prev) { var av = $("#iva-ya-conectado"); if (av) { av.hidden = false; $("a", av).href = "/iva/mi-cuenta/#" + prev; } }
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var err = $(".err", form); err.textContent = "";
      if (!form.reportValidity()) return;
      var d = {}; new FormData(form).forEach(function (v, k) { d[k] = String(v); });
      d.guardar = !!form.guardar.checked;
      d.autorizacion = form.autorizacion.checked ? "si" : "";
      d.autorizacion_texto = $("#txt-autorizacion").innerText;
      var btn = $("button[type=submit]", form); btn.disabled = true; btn.textContent = "Conectando con ARCA…";
      var prog = $("#iva-progreso");
      api("conectar", d).then(function (j) {
        form.clave.value = ""; d = null;
        if (!j.ok) throw new Error(j.error);
        form.hidden = true; prog.hidden = false;
        var link = location.origin + "/iva/mi-cuenta/#" + j.token;
        $("#iva-link").value = link; store.set(j.token);
        return esperar(j.token, j.consulta, function (s) { $("#iva-seg").textContent = s; }).then(function (est) {
          $("#iva-espera").hidden = true;
          renderResultado($("#iva-resultado"), est.consulta.resultado);
          $("#iva-post").hidden = false;
        });
      }).catch(function (e) {
        btn.disabled = false; btn.textContent = "Consultar mi IVA";
        if (!prog.hidden) { $("#iva-espera").innerHTML = "<p class='err'>" + e.message + "</p><p>Podés reintentar desde <a href='" + $("#iva-link").value + "'>tu panel</a>.</p>"; $("#iva-post").hidden = false; }
        else err.textContent = e.message;
      });
    });
    var cp = $("#iva-copiar");
    if (cp) cp.addEventListener("click", function () { navigator.clipboard.writeText($("#iva-link").value).then(function () { cp.textContent = "¡Copiado!"; }); });
  }

  // ---------- Panel (/iva/mi-cuenta/) ----------
  var panel = $("#iva-panel");
  if (panel) {
    var token = location.hash.slice(1) || store.get();
    if (location.hash) { store.set(token); history.replaceState(null, "", location.pathname); }
    var msg = $("#p-msg"), res = $("#p-resultado");
    if (!token) { msg.innerHTML = "No encontramos tu acceso en este navegador. Abrí el enlace privado que guardaste o <a href='/iva/'>conectá tu CUIT</a>."; return; }
    var cargar = function () {
      return api("estado", { token: token }).then(function (j) {
        if (!j.ok) { store.del(); msg.innerHTML = j.error + " <a href='/iva/'>Conectá tu CUIT de nuevo</a>."; return; }
        panel.hidden = false;
        $("#p-cuit").textContent = j.cuenta.cuit.replace(/^(\d{2})(\d{8})(\d)$/, "$1-$2-$3");
        $("#p-guardado").textContent = j.cuenta.guardar ? "Acceso guardado y cifrado: podés consultar cuando quieras." : "No guardamos tu acceso: para consultar vas a tener que ingresar la clave.";
        $("#p-reconectar").hidden = j.cuenta.guardar;
        var c = j.consulta;
        if (c && c.estado === "lista") renderResultado(res, c.resultado);
        else if (c && c.estado === "en_proceso") { msg.textContent = "Consultando ARCA…"; esperar(token, c.id).then(function () { msg.textContent = ""; cargar(); }).catch(function (e) { msg.textContent = e.message; }); }
        else if (c && c.estado === "error") msg.textContent = c.error;
        var h = j.historial || [];
        $("#p-hist").innerHTML = h.length ? "<div class='tbl'><table><thead><tr><th>Período</th><th class='num'>Débito</th><th class='num'>Crédito</th><th class='num'>Determinado</th></tr></thead><tbody>" +
          h.map(function (x) { return "<tr><td>" + nombreMes(x.periodo) + "</td><td class='num'>" + ars(x.debito) + "</td><td class='num'>" + ars(x.credito) + "</td><td class='num'>" + ars(x.determinado) + "</td></tr>"; }).join("") + "</tbody></table></div>" : "";
      });
    };
    var consultar = function (periodo) {
      msg.textContent = "Consultando ARCA… (suele tardar menos de un minuto)";
      var rc = $("#p-reconectar");
      var body = { token: token, periodo: periodo }, path = "consultar";
      if (!rc.hidden) { if (!$("#p-clave").value) { msg.textContent = "Ingresá tu clave fiscal para consultar."; return; } path = "reconectar"; body.clave = $("#p-clave").value; body.usuario = $("#p-usuario").value; body.guardar = $("#p-guardar").checked; }
      api(path, body).then(function (j) {
        $("#p-clave").value = "";
        if (!j.ok) { if (j.reconectar) $("#p-reconectar").hidden = false; throw new Error(j.error); }
        return esperar(token, j.consulta, function (s) { msg.textContent = "Consultando ARCA… " + s + " s"; });
      }).then(function () { msg.textContent = ""; return cargar(); }).catch(function (e) { msg.textContent = e.message; });
    };
    $("#p-actual").addEventListener("click", function () { consultar(periodoOffset(0)); });
    $("#p-anterior").addEventListener("click", function () { consultar(periodoOffset(1)); });
    $("#p-borrar").addEventListener("click", function () {
      if ($("#p-borrar").dataset.ok !== "1") { $("#p-borrar").dataset.ok = "1"; $("#p-borrar").textContent = "Confirmar: borrar mi acceso y mis datos"; return; }
      api("desconectar", { token: token }).then(function () { store.del(); panel.innerHTML = "<p class='result'>Listo: borramos tu acceso, tus consultas y tu cuenta. Te recomendamos cambiar tu clave fiscal si querés mayor tranquilidad.</p>"; });
    });
    cargar();
  }
})();
