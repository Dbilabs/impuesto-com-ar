#!/usr/bin/env python3
"""Genera la imagen para redes (OG 1200x630), el logo 512 y el apple-touch-icon en src/static.
Requiere: pip install playwright && playwright install chromium"""
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "src" / "static"
(OUT / "og").mkdir(parents=True, exist_ok=True)
MARK = ('<svg viewBox="0 0 32 32" width="{s}" height="{s}"><rect width="32" height="32" rx="8" fill="#0B6E4F"/>'
        '<path d="M9 17l4 4 10-10" stroke="#fff" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>')
FONT = "font-family:Inter,Roboto,'Liberation Sans','DejaVu Sans',Arial,sans-serif"
OG = f"""<html><body style="margin:0"><div style="width:1200px;height:630px;box-sizing:border-box;padding:72px 80px;background:#0F1B2D;color:#fff;{FONT};display:flex;flex-direction:column;justify-content:space-between">
<div style="display:flex;align-items:center;gap:16px;font-size:34px;font-weight:800">{MARK.format(s=56)}<span>impuestos<span style="color:#8FD3B6">.com.ar</span></span></div>
<div><div style="font-size:70px;font-weight:800;line-height:1.05;letter-spacing:-1.5px;max-width:960px">Tus impuestos bien llevados te hacen ganar plata</div>
<div style="font-size:32px;color:#C9D3DF;margin-top:22px">¿Qué no te está diciendo tu contador? Segunda opinión gratis.</div></div>
<div style="display:flex;gap:14px;font-size:24px;color:#8FD3B6;font-weight:600"><span>Monotributo</span>·<span>Empresas</span>·<span>Auditoría</span>·<span>ARCA</span></div></div></body></html>"""
ICON = f'<html><body style="margin:0">{MARK.format(s=512)}</body></html>'

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1200, "height": 630})
    pg.set_content(OG); pg.screenshot(path=str(OUT / "og" / "default.png"))
    pg.set_viewport_size({"width": 512, "height": 512}); pg.set_content(ICON); pg.screenshot(path=str(OUT / "logo-512.png"), omit_background=True)
    pg.set_viewport_size({"width": 180, "height": 180}); pg.set_content(f'<html><body style="margin:0;background:#0B6E4F">{MARK.format(s=180)}</body></html>')
    pg.screenshot(path=str(OUT / "apple-touch-icon.png"))
    b.close()
print("Imágenes generadas en", OUT)
