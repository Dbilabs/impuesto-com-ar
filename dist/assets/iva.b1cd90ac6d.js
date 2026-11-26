(function () {
  "use strict";
  var root = document.getElementById("iva-tool");
  if (!root) return;
  var $ = function (s) { return root.querySelector(s); };
  var ars = function (n) { return "$ " + Math.round(n).toLocaleString("es-AR"); };
  var num = function (v) {
    if (typeof v === "number") return v;
    var s = String(v == null ? "" : v).trim().replace(/\s|\$/g, "");
    if (!s) return 0;
    if (s.indexOf(",") > -1 || /^-?\d{1,3}(\.\d{3})+$/.test(s)) s = s.replace(/\./g, "").replace(",", ".");
    var n = parseFloat(s);
    return isNaN(n) ? 0 : n;
  };
  var norm = function (s) { return String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/\s+/g, " ").trim(); };
  var data = { emitidos: null, recibidos: null };

  // ---------- Lectura de archivos de "Mis Comprobantes" (CSV o Excel). Nada sale del navegador. ----------
  function parseCSV(text) {
    var first = text.split(/\r?\n/).slice(0, 5).join("\n");
    var d = (first.match(/;/g) || []).length > (first.match(/,/g) || []).length ? ";" : ",";
    var rows = [], row = [], cell = "", q = false;
    for (var i = 0; i < text.length; i++) {
      var c = text[i];
      if (q) { if (c === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; } else cell += c; }
      else if (c === '"') q = true;
      else if (c === d) { row.push(cell); cell = ""; }
      else if (c === "\n") { row.push(cell.replace(/\r$/, "")); rows.push(row); row = []; cell = ""; }
      else cell += c;
    }
    if (cell || row.length) { row.push(cell); rows.push(row); }
    return rows;
  }
  function loadXLSX() {
    return new Promise(function (ok, ko) {
      if (window.XLSX) return ok(window.XLSX);
      var s = document.createElement("script");
      s.src = "/assets/vendor/xlsx-0.20.3.min.js";
      s.onload = function () { ok(window.XLSX); }; s.onerror = ko;
      document.head.appendChild(s);
    });
  }
  function readRows(file) {
    var isX = /\.xlsx?$/i.test(file.name);
    return file.arrayBuffer().then(function (buf) {
      if (isX) return loadXLSX().then(function (X) { var wb = X.read(buf, { type: "array" }); return X.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]], { header: 1, raw: true }); });
      var t = new TextDecoder("utf-8").decode(buf);
      if (t.indexOf("�") > -1) t = new TextDecoder("iso-8859-1").decode(buf);
      return parseCSV(t.replace(/^﻿/, ""));
    });
  }
  function toMonth(v) {
    if (typeof v === "number") { var d = new Date(Math.round((v - 25569) * 864e5)); return d.getUTCFullYear() + "-" + String(d.getUTCMonth() + 1).padStart(2, "0"); }
    var s = String(v || "").trim(), m;
    if ((m = s.match(/^(\d{4})-(\d{2})/))) return m[1] + "-" + m[2];
    if ((m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/))) return m[3] + "-" + String(m[2]).padStart(2, "0");
    return null;
  }
  var NC = [3, 8, 13, 53, 203, 208, 213];
  function summarize(rows) {
    var h = -1;
    for (var i = 0; i < Math.min(rows.length, 15); i++) {
      var r = (rows[i] || []).map(norm);
      if (r.indexOf("fecha") > -1 && r.some(function (x) { return x === "tipo" || x.indexOf("tipo de comprobante") === 0; })) { h = i; break; }
    }
    if (h < 0) throw new Error("No encontramos los encabezados de Mis Comprobantes (Fecha, Tipo, IVA).");
    var H = rows[h].map(norm), col = function (fn) { for (var j = 0; j < H.length; j++) if (fn(H[j])) return j; return -1; };
    var cF = col(function (x) { return x === "fecha" || x.indexOf("fecha de emision") === 0; });
    var cT = col(function (x) { return x === "tipo" || x.indexOf("tipo de comprobante") === 0; });
    var cI = col(function (x) { return x === "total iva"; }); if (cI < 0) cI = col(function (x) { return x === "iva"; });
    var cN = col(function (x) { return x === "neto gravado total" || x === "imp. neto gravado" || x === "neto gravado"; });
    var cTC = col(function (x) { return x === "tipo cambio" || x === "tipo de cambio"; });
    if (cI < 0) throw new Error("El archivo no tiene la columna de IVA (\"Total IVA\" o \"IVA\").");
    var months = {};
    rows.slice(h + 1).forEach(function (r) {
      if (!r || r.length < 3) return;
      var mo = toMonth(r[cF]); if (!mo) return;
      var tipo = String(r[cT] == null ? "" : r[cT]), code = parseInt(tipo, 10);
      var sign = (NC.indexOf(code) > -1 || /nota de cr/i.test(tipo)) ? -1 : 1;
      var tc = cTC > -1 ? num(r[cTC]) : 1; if (!(tc > 0)) tc = 1;
      var m = months[mo] || (months[mo] = { iva: 0, neto: 0, n: 0 });
      m.iva += sign * num(r[cI]) * tc; m.neto += cN > -1 ? sign * num(r[cN]) * tc : 0; m.n++;
    });
    return months;
  }
  function refreshMonths() {
    var sel = $("#iva-mes"), set = {};
    ["emitidos", "recibidos"].forEach(function (k) { if (data[k]) Object.keys(data[k]).forEach(function (m) { set[m] = 1; }); });
    var ms = Object.keys(set).sort().reverse();
    sel.innerHTML = ms.map(function (m) { var p = m.split("-"); return "<option value='" + m + "'>" + ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"][+p[1] - 1] + " " + p[0] + "</option>"; }).join("");
    $("#iva-mes-wrap").hidden = !ms.length;
    applyMonth();
  }
  function applyMonth() {
    var m = $("#iva-mes").value, info = [];
    if (data.emitidos) { var e = data.emitidos[m] || { iva: 0, n: 0 }; $("#iva-deb").value = Math.round(e.iva).toLocaleString("es-AR"); info.push(e.n + " comprobantes emitidos"); }
    if (data.recibidos) { var r = data.recibidos[m] || { iva: 0, n: 0 }; $("#iva-cred").value = Math.round(r.iva).toLocaleString("es-AR"); info.push(r.n + " comprobantes recibidos"); }
    $("#iva-file-info").textContent = info.length ? "Tomamos " + info.join(" y ") + " del mes elegido." : "";
    calc();
  }
  ["emitidos", "recibidos"].forEach(function (k) {
    $("#f-" + k).addEventListener("change", function (ev) {
      var f = ev.target.files[0], st = $("#st-" + k); if (!f) return;
      st.textContent = "Leyendo…";
      readRows(f).then(function (rows) { data[k] = summarize(rows); st.textContent = "✓ " + f.name; refreshMonths(); })
        .catch(function (e) { data[k] = null; st.textContent = "No pudimos leer el archivo: " + (e.message || "formato no reconocido") + " Probá con el CSV de Mis Comprobantes."; });
    });
  });
  $("#iva-mes").addEventListener("change", applyMonth);

  // ---------- Cálculo ----------
  function calc() {
    var deb = num($("#iva-deb").value), cred = num($("#iva-cred").value), ret = num($("#iva-ret").value),
        stA = num($("#iva-sta").value), sldA = num($("#iva-sld").value);
    var out = $("#iva-out");
    if (!deb && !cred) { out.hidden = true; return; }
    out.hidden = false;
    var det = deb - cred - stA, nuevoST = det < 0 ? -det : 0, impDet = Math.max(det, 0);
    var pagar = impDet - ret - sldA, nuevoSLD = pagar < 0 ? -pagar : 0; pagar = Math.max(pagar, 0);
    var html = "<div class='grid' style='gap:12px'>" +
      "<div><span class='src'>Débito fiscal (ventas)</span><div style='font-weight:700;font-size:20px'>" + ars(deb) + "</div></div>" +
      "<div><span class='src'>Crédito fiscal (compras + saldo técnico)</span><div style='font-weight:700;font-size:20px'>" + ars(cred + stA) + "</div></div>" +
      "<div><span class='src'>Retenciones, percepciones y saldo libre</span><div style='font-weight:700;font-size:20px'>" + ars(ret + sldA) + "</div></div></div>";
    if (pagar > 0) {
      var compras = pagar / 0.21;
      html += "<p style='margin:16px 0 0'>IVA estimado a pagar este mes</p><p class='big' style='margin:0'>" + ars(pagar) + "</p>" +
        "<p><strong>Para planificar:</strong> compras gravadas al 21% por unos <strong>" + ars(compras) + " + IVA</strong> (" + ars(pagar) + " de IVA), facturadas a tu CUIT con fecha de este mes, llevarían el saldo a pagar a cero.</p>" +
        "<p class='src'>Ojo: comprar solo para compensar no ahorra impuesto, adelanta el crédito fiscal y usa caja. Conviene si la compra (stock, insumos, equipos) la ibas a hacer igual.</p>";
    } else {
      html += "<p style='margin:16px 0 0'>Este mes no pagarías IVA</p><p class='big' style='margin:0'>" + ars(0) + "</p>";
      if (nuevoST > 0) html += "<p>Te queda un <strong>saldo técnico a favor de " + ars(nuevoST) + "</strong> para el mes siguiente.</p>";
      if (nuevoSLD > 0) html += "<p>Y un <strong>saldo de libre disponibilidad de " + ars(nuevoSLD) + "</strong>, que en ciertos casos se puede compensar con otros impuestos o pedir en devolución.</p>";
      if (nuevoST > 0 && nuevoST > deb * 0.5) html += "<p class='src'>Si el saldo técnico se repite todos los meses, revisá con un especialista: puede haber retenciones o percepciones que conviene reducir.</p>";
    }
    html += "<a class='btn' href='/diagnostico/?perfil=ri&tema=iva-planificacion'>Que un especialista planifique mi IVA</a>";
    out.innerHTML = html;
  }
  root.addEventListener("input", function (e) { if (e.target.matches("input[type=text]")) calc(); });
})();
