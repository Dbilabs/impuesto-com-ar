"""
bot/scraper_bbpp.py
Scraper hardened para 'BIENES PERSONALES WEB' (F. 762 - siapweb.cloud.afip.gob.ar/f762/).
Navega correctamente la SPA AngularJS:
1. Abre el servicio desde el portal ARCA para heredar el token SAML oficial.
2. Lee próximo vencimiento en #/inicio.
3. Navega obligatoriamente a #/declaraciones.anteriores para extraer todo el historial real
   de DDJJ presentadas (evitando falsos negativos).
"""

import os
import re
from typing import Dict, Any, List
from playwright.sync_api import sync_playwright
from bot.scraper import _get_browser_path, _login_arca


def consultar_bienes_personales_web(usuario: str, clave: str) -> Dict[str, Any]:
    """
    Extrae el próximo vencimiento y el historial completo de declaraciones juradas
    presentadas en BIENES PERSONALES WEB (F. 762). Modo 100% lectura (sin impacto).
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=_get_browser_path(),
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        context = browser.new_context()
        page = context.new_page()

        try:
            _login_arca(page, usuario, clave)
            page.wait_for_timeout(2000)

            btn_ver_todos = page.query_selector("text='Ver todos'")
            if btn_ver_todos and btn_ver_todos.is_visible():
                btn_ver_todos.click()
                page.wait_for_timeout(1500)

            btn_bp = (
                page.query_selector("//h3[contains(text(), 'BIENES PERSONALES WEB')]/ancestor::a")
                or page.query_selector("a:has-text('BIENES PERSONALES WEB')")
            )
            if not btn_bp:
                return {
                    "ok": False,
                    "error": "No se encontró el servicio 'BIENES PERSONALES WEB' habilitado en el portal ARCA."
                }

            with context.expect_page(timeout=20000) as p_info:
                btn_bp.click()
            bp_page = p_info.value
            try:
                bp_page.wait_for_load_state("domcontentloaded", timeout=20000)
            except Exception:
                pass
            bp_page.wait_for_timeout(3000)

            # 1. Extraer próximo vencimiento desde #/inicio
            texto_inicio = bp_page.inner_text("body")
            venc_match = re.search(r"Declaración período\s+(\d{4})\s*-\s*vence el\s+(\d{2}/\d{2}/\d{4})", texto_inicio)
            proximo_vencimiento = None
            if venc_match:
                proximo_vencimiento = {
                    "periodo": venc_match.group(1),
                    "fecha_vencimiento": venc_match.group(2)
                }

            # 2. Navegar obligatoriamente a #/declaraciones.anteriores
            bp_page.goto(
                "https://siapweb.cloud.afip.gob.ar/f762/#/declaraciones.anteriores",
                wait_until="domcontentloaded",
                timeout=25000
            )
            bp_page.wait_for_timeout(3000)

            filas_raw = bp_page.evaluate("""() => {
                return Array.from(document.querySelectorAll("table tbody tr")).map(tr => {
                    return Array.from(tr.querySelectorAll("td")).map(td => td.innerText.trim());
                }).filter(cols => cols.length >= 3 && /^\\d{4}$/.test(cols[0]));
            }""")

            declaraciones: List[Dict[str, str]] = []
            for cols in filas_raw:
                # Formato nuevo (2017+): [Periodo, Establecimiento, Sustituyendo, Secuencia, Fecha, ...]
                # Formato viejo (2013-2016): [Periodo, Secuencia, Fecha, ...]
                if len(cols) >= 5 and re.match(r"\d{2}/\d{2}/\d{4}", cols[4]):
                    declaraciones.append({
                        "periodo": cols[0],
                        "secuencia": cols[3],
                        "fecha_presentacion": cols[4]
                    })
                elif len(cols) >= 3 and re.match(r"\d{2}/\d{2}/\d{4}", cols[2]):
                    declaraciones.append({
                        "periodo": cols[0],
                        "secuencia": cols[1],
                        "fecha_presentacion": cols[2]
                    })

            ultimo_periodo = declaraciones[0]["periodo"] if declaraciones else None
            return {
                "ok": True,
                "servicio": "BIENES PERSONALES WEB (F. 762)",
                "proximo_vencimiento": proximo_vencimiento,
                "total_presentaciones_historicas": len(declaraciones),
                "ultimo_periodo_presentado": ultimo_periodo,
                "declaraciones_presentadas": declaraciones
            }
        finally:
            browser.close()
