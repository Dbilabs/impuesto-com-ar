"""
scripts/record_demo_video.py
Graba un video real (.mp4 H.264 + poster .png) de una sesión en vivo con el look & feel
exacto de Claude Desktop / Claude.ai conectado a impuesto-arca-mcp (ARCA).
"""

import os
import glob
import subprocess
import tempfile
from playwright.sync_api import sync_playwright

OUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src", "static", "assets"))
os.makedirs(OUT_DIR, exist_ok=True)
MP4_OUT = os.path.join(OUT_DIR, "demo-claude-arca.mp4")
POSTER_OUT = os.path.join(OUT_DIR, "demo-claude-poster.png")

HTML_SCENE = """<!doctype html>
<html lang="es-AR">
<head>
<meta charset="utf-8">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    width: 1280px; height: 720px; overflow: hidden;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #FAF9F5; color: #1F1E1D; display: flex;
  }
  .sidebar {
    width: 248px; background: #F0EFEA; border-right: 1px solid #E3E2DC;
    padding: 18px 14px; display: flex; flex-direction: column; gap: 14px;
  }
  .brand { display: flex; align-items: center; gap: 9px; font-weight: 700; font-size: 16px; color: #1F1E1D; padding: 4px 6px; }
  .spark { width: 24px; height: 24px; border-radius: 6px; background: #D97757; color: #fff; display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 14px; }
  .sec-lbl { font-size: 11px; font-weight: 700; color: #7C7A74; text-transform: uppercase; letter-spacing: 0.06em; padding: 6px 8px 2px; }
  .nav-item { padding: 8px 10px; border-radius: 8px; font-size: 13px; color: #3D3C38; display: flex; align-items: center; justify-content: space-between; }
  .nav-item.active { background: #E5E4DE; font-weight: 600; color: #141413; }
  .mcp-badge { margin-top: auto; background: #fff; border: 1px solid #DFDDD6; border-radius: 10px; padding: 10px 12px; font-size: 12px; }
  .dot-on { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #0B6E4F; margin-right: 6px; }

  .main { flex: 1; display: flex; flex-direction: column; height: 720px; }
  .topbar {
    height: 52px; border-bottom: 1px solid #E8E6DF; padding: 0 28px;
    display: flex; align-items: center; justify-content: space-between; background: #FAF9F5;
  }
  .topbar-title { font-size: 14px; font-weight: 600; color: #2C2B28; }
  .model-pill { font-size: 12px; color: #6B6963; background: #F0EFEA; padding: 4px 10px; border-radius: 99px; border: 1px solid #E3E2DC; }

  .chat { flex: 1; padding: 24px 64px; overflow: hidden; display: flex; flex-direction: column; gap: 18px; }

  .user-msg {
    align-self: flex-end; max-width: 78%; background: #EFECE6; border: 1px solid #E3DFD7;
    padding: 13px 18px; border-radius: 16px 16px 4px 16px; font-size: 14.5px; line-height: 1.45; color: #1F1E1D;
    opacity: 0; transform: translateY(8px); transition: all 0.35s ease;
  }
  .user-msg.show { opacity: 1; transform: translateY(0); }
  .attach-pill { display: inline-flex; align-items: center; gap: 6px; margin-top: 8px; background: #fff; border: 1px solid #DCD9D0; border-radius: 8px; padding: 4px 10px; font-size: 12px; color: #4A4843; font-weight: 500; }

  .claude-row { display: flex; gap: 14px; align-items: flex-start; opacity: 0; transform: translateY(8px); transition: all 0.4s ease; }
  .claude-row.show { opacity: 1; transform: translateY(0); }
  .claude-av {
    width: 30px; height: 30px; border-radius: 50%; background: #D97757; color: #fff;
    display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 15px; flex-shrink: 0; margin-top: 2px;
  }
  .claude-body { flex: 1; display: flex; flex-direction: column; gap: 10px; }

  .tool-call {
    background: #F4F3EE; border: 1px solid #E2E0D8; border-radius: 10px; padding: 8px 13px;
    font-size: 12.5px; color: #4B4A45; display: flex; align-items: center; justify-content: space-between;
    opacity: 0; transform: translateY(6px); transition: all 0.3s ease;
  }
  .tool-call.show { opacity: 1; transform: translateY(0); }
  .tool-name { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-weight: 600; color: #2D2C28; }
  .tool-ok { color: #0B6E4F; font-weight: 700; font-size: 12px; }

  .answer-card {
    background: #fff; border: 1px solid #E4E2DA; border-radius: 14px; padding: 16px 20px;
    box-shadow: 0 4px 18px rgba(0,0,0,0.03); opacity: 0; transform: translateY(8px); transition: all 0.45s ease;
  }
  .answer-card.show { opacity: 1; transform: translateY(0); }
  .ans-grid { display: grid; grid-template-columns: 1.15fr 1fr; gap: 18px; margin-top: 10px; }
  .inv-box { background: #FAF9F5; border: 1px solid #E5E3DC; border-radius: 10px; padding: 12px 14px; font-size: 12.5px; line-height: 1.55; }
  .chart-box { background: #FAF9F5; border: 1px solid #E5E3DC; border-radius: 10px; padding: 12px 14px; font-size: 12px; }

  .actions { display: flex; gap: 10px; margin-top: 12px; opacity: 0; transition: opacity 0.4s ease; }
  .actions.show { opacity: 1; }
  .btn-ok { background: #0B6E4F; color: #fff; padding: 7px 14px; border-radius: 8px; font-size: 12.5px; font-weight: 600; }
  .btn-hitl { background: #F4F3EE; color: #1F1E1D; border: 1px solid #D8D6CE; padding: 7px 14px; border-radius: 8px; font-size: 12.5px; font-weight: 600; }

  .inputbar {
    margin: 0 64px 18px; background: #fff; border: 1px solid #DDDAD1; border-radius: 14px;
    padding: 12px 16px; display: flex; align-items: center; justify-content: space-between;
    font-size: 13.5px; color: #8A877F; box-shadow: 0 2px 10px rgba(0,0,0,0.03);
  }
  .send-btn { width: 30px; height: 30px; border-radius: 8px; background: #D97757; color: #fff; display: flex; align-items: center; justify-content: center; font-weight: 800; }
</style>
</head>
<body>
  <aside class="sidebar">
    <div class="brand"><div class="spark">✦</div> Claude</div>
    <div>
      <div class="sec-lbl">Proyecto</div>
      <div class="nav-item active"><span>📁 Impuestos · Innovatech</span></div>
    </div>
    <div>
      <div class="sec-lbl">Chats del Mes</div>
      <div class="nav-item active"><span>Cierre Noviembre 2026</span></div>
      <div class="nav-item"><span>Cierre Octubre 2026</span></div>
      <div class="nav-item"><span>Renovación MiPyME F.1272</span></div>
    </div>
    <div class="mcp-badge">
      <div style="font-weight:700;color:#1F1E1D;margin-bottom:3px"><span class="dot-on"></span>impuesto-arca-mcp</div>
      <div style="color:#6E6C66;font-size:11px">43 herramientas ARCA activas · D1 sync</div>
    </div>
  </aside>

  <main class="main">
    <header class="topbar">
      <div class="topbar-title">Impuestos · Innovatech Solutions S.R.L. — Cierre Noviembre 2026</div>
      <div class="model-pill">Claude Sonnet · MCP Conectado</div>
    </header>

    <section class="chat">
      <div class="user-msg" id="u1">
        <div id="typed"></div>
        <div class="attach-pill" id="att" style="display:none">📎 Extracto_Galicia_Nov2026.pdf · 412 KB</div>
      </div>

      <div class="claude-row" id="c1">
        <div class="claude-av">✦</div>
        <div class="claude-body">
          <div class="tool-call" id="t1">
            <span>⚡ <span class="tool-name">impuesto-arca-mcp · emitir_factura_wsfe</span> (WSFEv1 · &lt;1s)</span>
            <span class="tool-ok" id="t1s">Ejecutando...</span>
          </div>
          <div class="tool-call" id="t2">
            <span>⚡ <span class="tool-name">impuesto-arca-mcp · verificar_proveedor_apocrifo_apoc</span></span>
            <span class="tool-ok" id="t2s">Auditando...</span>
          </div>
          <div class="tool-call" id="t3">
            <span>⚡ <span class="tool-name">impuesto-arca-mcp · conciliar_y_graficar_pelicula_fiscal</span></span>
            <span class="tool-ok" id="t3s">Conciliando PDF...</span>
          </div>

          <div class="answer-card" id="card">
            <div style="font-size:14px;font-weight:700;color:#1F1E1D">Listo. Factura A autorizada en ARCA y cierre mensual conciliado con tu extracto Galicia:</div>
            <div class="ans-grid">
              <div class="inv-box">
                <div style="font-weight:700;color:#0B6E4F;margin-bottom:4px">📄 FACTURA A · 00001-00000042</div>
                <div><strong>Cliente:</strong> Distribuidora Andina S.A. (30-71888888-2)</div>
                <div><strong>Neto:</strong> $1.500.000 · <strong>IVA 21%:</strong> $315.000</div>
                <div><strong>Total:</strong> $1.815.000 · <strong>CAE:</strong> <code>76479812340012</code></div>
                <div style="margin-top:6px;color:#0B6E4F;font-weight:600">✓ QR RG 4892 y PDF A4 generados · Proveedores e-APOC 100% limpios</div>
              </div>
              <div class="chart-box">
                <div style="font-weight:700;color:#1F1E1D;margin-bottom:8px">📊 Ahorro rescatado de tu extracto Galicia</div>
                <div style="margin-bottom:8px">
                  <div style="display:flex;justify-content:space-between;margin-bottom:3px"><span>IVA estimado solo con ARCA</span><strong style="color:#DC2626">$1.200.000</strong></div>
                  <div style="background:#E6E4DC;height:10px;border-radius:99px"><div style="background:#DC2626;width:100%;height:100%;border-radius:99px"></div></div>
                </div>
                <div style="margin-bottom:8px">
                  <div style="display:flex;justify-content:space-between;margin-bottom:3px"><span>Con Impuesto al Cheque + SIRCREB</span><strong style="color:#0B6E4F">$531.000 (-55%)</strong></div>
                  <div style="background:#E6E4DC;height:10px;border-radius:99px"><div style="background:#0B6E4F;width:45%;height:100%;border-radius:99px"></div></div>
                </div>
                <div style="color:#0B6E4F;font-weight:700;font-size:12px">💡 Sugerencia CFO: Tenés Certificado MiPyME activo → diferí el pago de IVA a 90 días.</div>
              </div>
            </div>
            <div class="actions" id="acts">
              <div class="btn-ok">✓ Confirmar F. 2002 en ARCA</div>
              <div class="btn-hitl">👨‍💼 Pedir revisión de Contador Matriculado</div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <div class="inputbar">
      <span>Escribile a Claude sobre tus impuestos, facturas o vencimientos...</span>
      <div class="send-btn">↑</div>
    </div>
  </main>
</body>
</html>"""


def main():
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    with tempfile.TemporaryDirectory() as tmpdir:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=chrome if os.path.exists(chrome) else None)
            context = browser.new_context(viewport={"width": 1280, "height": 720})
            page = context.new_page()
            page.set_content(HTML_SCENE, wait_until="load")
            page.wait_for_timeout(300)

            frame_idx = 0
            def snap(repeat=1):
                nonlocal frame_idx
                p0 = os.path.join(tmpdir, f"f_{frame_idx:04d}.png")
                page.screenshot(path=p0)
                frame_idx += 1
                for _ in range(repeat - 1):
                    p_dup = os.path.join(tmpdir, f"f_{frame_idx:04d}.png")
                    os.link(p0, p_dup)
                    frame_idx += 1

            # 0. Initial empty Claude screen (0.6s @ 10fps)
            snap(6)

            # 1. User types prompt smoothly
            page.evaluate("document.getElementById('u1').classList.add('show')")
            page.wait_for_timeout(380)
            prompt = "Facturale a Distribuidora Andina S.A. $1.500.000 + IVA desde Innovatech S.R.L., auditá proveedores y cruzá mi extracto Galicia para cerrar el IVA."
            for i in range(0, len(prompt) + 1, 8):
                chunk = prompt[:i].replace("'", "\\'")
                page.evaluate(f"document.getElementById('typed').innerText = '{chunk}'")
                snap(1)
            page.evaluate(f"document.getElementById('typed').innerText = '{prompt}'")
            page.evaluate("document.getElementById('att').style.display = 'inline-flex'")
            snap(8)

            # 2. Claude responds & executes 3 MCP tools sequentially
            page.evaluate("document.getElementById('c1').classList.add('show')")
            page.evaluate("document.getElementById('t1').classList.add('show')")
            page.wait_for_timeout(420)
            snap(8)
            page.evaluate("document.getElementById('t1s').innerText = '✓ CAE 76479812340012'")
            snap(5)

            page.evaluate("document.getElementById('t2').classList.add('show')")
            page.wait_for_timeout(350)
            snap(7)
            page.evaluate("document.getElementById('t2s').innerText = '🟢 Limpio (e-APOC)'")
            snap(5)

            page.evaluate("document.getElementById('t3').classList.add('show')")
            page.wait_for_timeout(350)
            snap(8)
            page.evaluate("document.getElementById('t3s').innerText = '✓ +$292.000 rescatados'")
            snap(5)

            # 3. Render Invoice + Visual Chart + Human-in-the-Loop
            page.evaluate("document.getElementById('card').classList.add('show')")
            page.wait_for_timeout(480)
            snap(10)
            page.evaluate("document.getElementById('acts').classList.add('show')")
            page.wait_for_timeout(450)

            # Save crisp poster screenshot of the completed state
            page.screenshot(path=POSTER_OUT)
            snap(38)  # Hold final state 3.8s

            context.close()
            browser.close()

        # Stitch frames into crisp H.264 MP4 (10fps input -> 24fps smooth web playback)
        subprocess.run([
            "ffmpeg", "-y", "-framerate", "10",
            "-i", os.path.join(tmpdir, "f_%04d.png"),
            "-c:v", "libx264", "-r", "24", "-pix_fmt", "yuv420p",
            "-preset", "fast", "-crf", "22",
            "-movflags", "+faststart",
            MP4_OUT
        ], check=True, capture_output=True)

        size_kb = os.path.getsize(MP4_OUT) // 1024
        print(f"✓ Video MP4 real generado: {MP4_OUT} ({size_kb} KB, {frame_idx} frames)")
        print(f"✓ Poster PNG generado: {POSTER_OUT}")


if __name__ == "__main__":
    main()
