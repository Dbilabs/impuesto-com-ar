(function () {
  var SCENARIOS = {
    pyme: {
      chatTitle: "Impuestos · Innovatech Solutions S.R.L. — Cierre Noviembre 2026",
      prompt: "Facturale a Distribuidora Andina S.A. $1.500.000 + IVA desde Innovatech Solutions S.R.L., verificá proveedores en e-APOC y cruzá mi extracto Galicia para bajar el IVA.",
      attachment: "📎 Extracto_Galicia_Nov2026.pdf · 412 KB",
      tools: [
        { name: "impuesto-arca-mcp · emitir_factura_wsfe", meta: "WSFEv1 · 0.6s", done: "✓ CAE 74459201948210" },
        { name: "impuesto-arca-mcp · verificar_proveedor_apocrifo_apoc", meta: "Base e-APOC", done: "🟢 100% Limpio" },
        { name: "impuesto-arca-mcp · conciliar_y_graficar_pelicula_fiscal", meta: "Cruce PDF", done: "✓ +$292.000 ahorrados" }
      ],
      resultHtml:
        '<p style="margin:0 0 12px;font-weight:700;color:#1F1E1D">Listo. Factura A autorizada por Web Service oficial y cierre de IVA conciliado con tu extracto Galicia:</p>' +
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px;margin-bottom:12px">' +
          '<div style="background:#FAF9F5;border:1px solid #E5E3DC;border-radius:10px;padding:12px 14px;font-size:13px;line-height:1.55">' +
            '<div style="font-weight:700;color:#0B6E4F;margin-bottom:4px">📄 FACTURA A · 00001-00000128</div>' +
            '<div><strong>Receptor:</strong> Distribuidora Andina S.A. (RI)</div>' +
            '<div><strong>Neto:</strong> $1.500.000 · <strong>IVA 21%:</strong> $315.000</div>' +
            '<div><strong>Total:</strong> $1.815.000 · <strong>CAE:</strong> <code>74459201948210</code></div>' +
            '<div style="margin-top:5px;color:#0B6E4F;font-weight:600">✓ PDF A4 + QR RG 4892 generado</div>' +
          '</div>' +
          '<div style="background:#FAF9F5;border:1px solid #E5E3DC;border-radius:10px;padding:12px 14px;font-size:12.5px">' +
            '<div style="font-weight:700;margin-bottom:8px">📊 Impacto de adjuntar tu extracto bancario</div>' +
            '<div style="margin-bottom:7px"><div style="display:flex;justify-content:space-between;margin-bottom:3px"><span>Solo con ARCA</span><strong style="color:#DC2626">$1.200.000</strong></div><div style="background:#E6E4DC;height:8px;border-radius:99px"><div style="background:#DC2626;width:100%;height:100%;border-radius:99px"></div></div></div>' +
            '<div><div style="display:flex;justify-content:space-between;margin-bottom:3px"><span>Conciliado (Cheque + SIRCREB)</span><strong style="color:#0B6E4F">$531.000 (-55%)</strong></div><div style="background:#E6E4DC;height:8px;border-radius:99px"><div style="background:#0B6E4F;width:45%;height:100%;border-radius:99px"></div></div></div>' +
          '</div>' +
        '</div>' +
        '<div style="background:#E7F5EF;border-left:4px solid #0B6E4F;padding:10px 14px;border-radius:0 8px 8px 0;color:#074F39;font-size:13.5px;margin-bottom:12px">' +
          '<strong>Sugerencia CFO:</strong> Tenés Certificado MiPyME (F. 1272) vigente → podés diferir el pago de este IVA a 90 días y financiar capital de trabajo a tasa 0%.' +
        '</div>' +
        '<div style="display:flex;gap:10px;flex-wrap:wrap"><span style="background:#0B6E4F;color:#fff;padding:7px 14px;border-radius:8px;font-size:13px;font-weight:600">✓ Confirmar F. 2002 en ARCA</span><span style="background:#F3F2EC;color:#1F1E1D;border:1px solid #D8D6CE;padding:7px 14px;border-radius:8px;font-size:13px;font-weight:600">👨‍💼 Revisar con Contador Matriculado</span></div>'
    },
    mono: {
      chatTitle: "Impuestos · Lucas Martínez (UX) — Control Monotributo Nov 2026",
      prompt: "¿Cómo vengo con mi tope de Monotributo este mes, cuánto puedo facturar todavía sin saltar de categoría y tengo deuda en CCMA?",
      attachment: "",
      tools: [
        { name: "impuesto-arca-mcp · consultar_situacion_monotributo", meta: "Portal ARCA", done: "✓ Cat. C · 85,2% usado" },
        { name: "impuesto-arca-mcp · consultar_ccma_cuenta_corriente", meta: "CCMA Vivo", done: "⚠️ 1 cuota impaga" }
      ],
      resultHtml:
        '<div style="display:flex;justify-content:space-between;margin-bottom:8px;flex-wrap:wrap;gap:6px"><strong>LUCAS MARTÍNEZ · Categoría C (Servicios)</strong><span style="color:#B45309;font-weight:700">85,2% del tope anual consumido</span></div>' +
        '<div style="background:#E6E4DC;border-radius:999px;height:10px;overflow:hidden;margin-bottom:12px"><div style="background:linear-gradient(90deg,#0B6E4F 0%,#D97706 78%,#DC2626 100%);width:85.2%;height:100%"></div></div>' +
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:8px;font-size:13.5px;color:#475467;margin-bottom:12px">' +
          '<div>Facturado 12 meses: <strong>$21.024.029</strong></div>' +
          '<div>Tope Categoría C: <strong>$24.670.494</strong></div>' +
          '<div>Margen seguro: <strong style="color:#0B6E4F">$3.646.465</strong></div>' +
          '<div>Próxima Recategorización: <strong>Enero 2027</strong></div>' +
        '</div>' +
        '<div style="background:#FEF3C7;border-left:4px solid #D97706;padding:10px 14px;border-radius:0 8px 8px 0;color:#78350F;font-size:13.5px;margin-bottom:12px">' +
          '<strong>Alerta CCMA + Consejo:</strong> Tenés la cuota de Noviembre impaga ($66.020,12). Conviene abonarla hoy con QR antes de que corran intereses. Además, si vas a cobrar proyectos en USD del exterior, emití Factura E para aprovechar el cupo BCRA de USD 24.000 sin pesificar.' +
        '</div>' +
        '<div style="display:flex;gap:10px;flex-wrap:wrap"><span style="background:#0B6E4F;color:#fff;padding:7px 14px;border-radius:8px;font-size:13px;font-weight:600">Generar VEP / QR de Pago</span><span style="background:#F3F2EC;color:#1F1E1D;border:1px solid #D8D6CE;padding:7px 14px;border-radius:8px;font-size:13px;font-weight:600">Simular pase a Categoría D</span></div>'
    },
    estudio: {
      chatTitle: "Estudio Contable Rivera & Asociados — Revisión Socio (120 Clientes)",
      prompt: "Mostrame el tablero de cierres de IVA que cargó Sofía hoy, marcame desvíos raros respecto al mes pasado y prepará el reporte Marca Blanca de los aprobados.",
      attachment: "",
      tools: [
        { name: "impuesto-arca-mcp · tablero_cartera_estudio", meta: "D1 Multi-Cliente", done: "✓ 4 clientes · 1 anomalía roja" },
        { name: "impuesto-arca-mcp · generar_reporte_marca_blanca_cliente", meta: "WhatsApp B2B", done: "✓ Reporte listo" }
      ],
      resultHtml:
        '<p style="margin:0 0 10px;font-weight:700;color:#1F1E1D">Resumen de cartera de Sofía (Período 2026-11) — Control Junior → Socio:</p>' +
        '<div style="border:1px solid #E5E3DC;border-radius:10px;overflow:hidden;margin-bottom:12px;font-size:13px">' +
          '<div style="display:grid;grid-template-columns:1.4fr .9fr .9fr 1fr;background:#F3F2EC;padding:8px 12px;font-weight:700;color:#475467"><div>Cliente</div><div>IVA Actual</div><div>Desvío</div><div>Estado</div></div>' +
          '<div style="display:grid;grid-template-columns:1.4fr .9fr .9fr 1fr;padding:9px 12px;border-top:1px solid #E5E3DC;background:#FEF2F2;align-items:center"><div><strong>Innovatech S.R.L.</strong></div><div>$1.050.000</div><div style="color:#DC2626;font-weight:700">+162,5%</div><div style="color:#DC2626;font-weight:700">🔴 Anomalía</div></div>' +
          '<div style="display:grid;grid-template-columns:1.4fr .9fr .9fr 1fr;padding:9px 12px;border-top:1px solid #E5E3DC;background:#fff;align-items:center"><div><strong>Distribuidora Andina</strong></div><div>$1.820.000</div><div style="color:#0B6E4F;font-weight:600">+4,0%</div><div style="color:#0B6E4F;font-weight:700">🟢 Listo Socio</div></div>' +
        '</div>' +
        '<div style="background:#E7F5EF;border-left:4px solid #0B6E4F;padding:10px 14px;border-radius:0 8px 8px 0;color:#074F39;font-size:13.5px;margin-bottom:12px">' +
          '<strong>Hallazgo automático:</strong> Frené el cierre de <em>Innovatech S.R.L.</em> porque saltó +162,5% (falta imputar factura de AWS y crédito bancario). El de <em>Distribuidora Andina</em> está normal y ya tiene su mensaje Marca Blanca firmado por <em>Estudio Rivera &amp; Asociados</em>.' +
        '</div>' +
        '<div style="display:flex;gap:10px;flex-wrap:wrap"><span style="background:#0B6E4F;color:#fff;padding:7px 14px;border-radius:8px;font-size:13px;font-weight:600">✓ Aprobar normales en bloque (Socio)</span><span style="background:#F3F2EC;color:#1F1E1D;border:1px solid #D8D6CE;padding:7px 14px;border-radius:8px;font-size:13px;font-weight:600">📤 Copiar WhatsApp Marca Blanca</span></div>'
    },
    defensa: {
      chatTitle: "Defensa Fiscal · Jurisprudencia CSJN y Convenio Multilateral",
      prompt: "Un municipio de PBA donde solo despachamos encomiendas sin tener local nos intimó Tasa de Seguridad e Higiene, y el banco nos retuvo 4% de SIRCREB. ¿Qué hacemos?",
      attachment: "",
      tools: [
        { name: "impuesto-arca-mcp · consultar_jurisprudencia_fiscal", meta: "CSJN / TFN", done: "✓ Raffo + Esso c/ Quilmes" },
        { name: "impuesto-arca-mcp · consultar_tasas_provinciales_municipales", meta: "PBA · ARBA · SIFERE", done: "✓ Plan de descargo listo" }
      ],
      resultHtml:
        '<p style="margin:0 0 10px;font-weight:700;color:#1F1E1D">Tenés defensa constitucional sólida en ambos frentes:</p>' +
        '<div style="display:grid;gap:8px;margin-bottom:12px;font-size:13.5px">' +
          '<div style="background:#FAF9F5;border:1px solid #E5E3DC;border-radius:9px;padding:10px 14px"><strong>1. Tasa Municipal (TISH) improcedente:</strong> Por doctrina de la Corte Suprema (<em>Laboratorios Raffo</em> y <em>Esso c/ Quilmes</em>), ningún municipio puede cobrar tasa de inspección sin establecimiento físico ni servicio efectivamente prestado en su ejido.</div>' +
          '<div style="background:#FAF9F5;border:1px solid #E5E3DC;border-radius:9px;padding:10px 14px"><strong>2. Retención SIRCREB del 4%:</strong> Ocurre por operar interjurisdiccionalmente sin coeficientes unificados al día. Presentamos CM03 (SIFERE) y pedimos reducción de alícuota al tramo mínimo (0,01%–1,5%) más exclusión por saldo a favor.</div>' +
        '</div>' +
        '<div style="display:flex;gap:10px;flex-wrap:wrap"><span style="background:#0B6E4F;color:#fff;padding:7px 14px;border-radius:8px;font-size:13px;font-weight:600">📜 Generar borrador de descargo legal</span><span style="background:#F3F2EC;color:#1F1E1D;border:1px solid #D8D6CE;padding:7px 14px;border-radius:8px;font-size:13px;font-weight:600">👨‍💼 Validar con Tributarista Humano</span></div>'
    }
  };

  var activeTimers = [];
  function clearTimers() {
    while (activeTimers.length) clearTimeout(activeTimers.pop());
  }

  window.runClaudeScenario = function (key) {
    var sc = SCENARIOS[key] || SCENARIOS.pyme;
    clearTimers();

    // Active pill state
    document.querySelectorAll(".c-scen-btn").forEach(function (b) {
      b.classList.toggle("active", b.getAttribute("data-scen") === key);
    });

    var titleEl = document.getElementById("cd-title");
    var userBox = document.getElementById("cd-user-box");
    var userTxt = document.getElementById("cd-user-txt");
    var userAtt = document.getElementById("cd-user-att");
    var claudeRow = document.getElementById("cd-claude-row");
    var toolsBox = document.getElementById("cd-tools");
    var ansBox = document.getElementById("cd-answer");

    if (!userTxt) return;

    titleEl.textContent = sc.chatTitle;
    userTxt.textContent = "";
    userAtt.style.display = "none";
    userAtt.textContent = sc.attachment || "";
    userBox.style.opacity = "1";
    claudeRow.style.display = "none";
    toolsBox.innerHTML = "";
    ansBox.style.display = "none";
    ansBox.innerHTML = "";

    // 1. Smooth fast typing of user prompt
    var text = sc.prompt;
    var step = 6;
    var delay = 0;
    for (var i = step; i <= text.length + step; i += step) {
      (function (pos, t) {
        activeTimers.push(setTimeout(function () {
          userTxt.textContent = text.slice(0, pos);
        }, t));
      })(i, delay);
      delay += 22;
    }

    if (sc.attachment) {
      activeTimers.push(setTimeout(function () {
        userAtt.style.display = "inline-flex";
      }, delay + 80));
      delay += 220;
    }

    // 2. Show Claude row & animate each MCP tool call sequentially
    delay += 180;
    activeTimers.push(setTimeout(function () {
      claudeRow.style.display = "flex";
    }, delay));

    sc.tools.forEach(function (tool, idx) {
      var startAt = delay + 120 + idx * 520;
      activeTimers.push(setTimeout(function () {
        var row = document.createElement("div");
        row.className = "c-anim";
        row.style.cssText = "background:#F3F2EC;border:1px solid #E2E0D8;border-radius:9px;padding:7px 12px;font-size:12.5px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px";
        row.innerHTML =
          '<span>⚡ <code style="font-weight:600;color:#1F1E1D">' + tool.name + '</code> <span style="color:#6E6C66">(' + tool.meta + ')</span></span>' +
          '<span id="cd-ts-' + idx + '" style="color:#6E6C66;font-weight:600">Ejecutando...</span>';
        toolsBox.appendChild(row);
      }, startAt));

      activeTimers.push(setTimeout(function () {
        var st = document.getElementById("cd-ts-" + idx);
        if (st) {
          st.textContent = tool.done;
          st.style.color = "#0B6E4F";
          st.style.fontWeight = "700";
        }
      }, startAt + 380));
    });

    // 3. Reveal animated answer card
    var revealAt = delay + 220 + sc.tools.length * 520;
    activeTimers.push(setTimeout(function () {
      ansBox.innerHTML = sc.resultHtml;
      ansBox.style.display = "block";
      ansBox.className = "c-anim";
    }, revealAt));
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { window.runClaudeScenario("pyme"); });
  } else {
    window.runClaudeScenario("pyme");
  }
})();
