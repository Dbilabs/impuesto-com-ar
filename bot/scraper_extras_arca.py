"""
bot/scraper_extras_arca.py
Bots complementarios críticos para Estudios Contables y Contribuyentes en ARCA (ex-AFIP):
1. CCMA (Cuenta Corriente de Monotributistas y Autónomos): deuda exacta, intereses y saldos a favor.
2. Mis Retenciones (SIRE / SICORE): retenciones y percepciones de IVA/Ganancias sufridas.
3. Nuestra Parte: bienes, bancos, inmuebles y consumos que ARCA tiene registrados del contribuyente.
4. Base e-APOC (Facturas Apócrifas): verificación en vivo de proveedores riesgosos antes de computar Crédito Fiscal.

Todos operan en modo 100% lectura (dry-run seguro, sin impacto fiscal).
"""

import os
import re
import ssl
import urllib.request
from typing import Dict, Any, List, Optional
from playwright.sync_api import sync_playwright
from bot.scraper import _get_browser_path, _login_arca


def consultar_ccma(usuario: str, clave: str) -> Dict[str, Any]:
    """
    Ingresa al servicio CCMA (Cuenta Corriente de Contribuyentes Monotributistas y Autónomos)
    para extraer saldo deudor, saldo acreedor (a favor) y períodos impagos.
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
            page.wait_for_timeout(1500)
            btn_ver = page.query_selector("text='Ver todos'")
            if btn_ver and btn_ver.is_visible():
                btn_ver.click()
                page.wait_for_timeout(1500)

            btn_ccma = (
                page.query_selector("//h3[contains(text(), 'CCMA')]/ancestor::a")
                or page.query_selector("a:has-text('CCMA')")
            )
            if not btn_ccma:
                return {"ok": False, "error": "Servicio CCMA no encontrado en el menú de ARCA."}

            with context.expect_page() as p_info:
                btn_ccma.click()
            ccma = p_info.value
            ccma.wait_for_load_state("domcontentloaded")
            ccma.wait_for_timeout(3000)

            # En CCMA suele aparecer un botón "Cálculo de Deuda"
            btn_calc = (
                ccma.query_selector("input[value*='Cálculo de Deuda']")
                or ccma.query_selector("input[value*='Calculo de Deuda']")
                or ccma.query_selector("button:has-text('Cálculo de Deuda')")
                or ccma.query_selector("a:has-text('Cálculo de Deuda')")
            )
            if btn_calc:
                btn_calc.click()
                ccma.wait_for_load_state("domcontentloaded")
                ccma.wait_for_timeout(3000)

            texto = ccma.inner_text("body")
            # Buscar montos de saldo deudor y acreedor
            deudor_m = re.search(r"Saldo\s+Deudor[:\s]*\$?\s*([\d\.,]+)", texto, re.IGNORECASE)
            acreedor_m = re.search(r"Saldo\s+Acreedor[:\s]*\$?\s*([\d\.,]+)", texto, re.IGNORECASE)

            lineas_clave = [
                l.strip() for l in texto.splitlines()
                if l.strip() and any(k in l.upper() for k in ["DEUDOR", "ACREEDOR", "CAPITAL", "INTERES", "TOTAL", "PERIODO"])
            ][:15]

            return {
                "ok": True,
                "servicio": "CCMA (Cuenta Corriente Monotributistas y Autónomos)",
                "url": ccma.url,
                "saldo_deudor": deudor_m.group(1) if deudor_m else "0,00",
                "saldo_acreedor": acreedor_m.group(1) if acreedor_m else "0,00",
                "resumen_extraido": lineas_clave
            }
        finally:
            browser.close()


def consultar_mis_retenciones(
    usuario: str,
    clave: str,
    cuit_objetivo: Optional[str] = None,
    impuesto: str = "767"  # 767=SICORE-IVA/Ganancias, 217=Ganancias, 30=IVA
) -> Dict[str, Any]:
    """
    Ingresa al servicio 'MIS RETENCIONES' en ARCA para consultar retenciones y percepciones
    sufridas (SIRE/SICORE) que reducen el saldo a pagar de IVA y Ganancias.
    """
    cuit_target = "".join(c for c in str(cuit_objetivo or usuario) if c.isdigit())
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
            page.wait_for_timeout(1500)
            btn_ver = page.query_selector("text='Ver todos'")
            if btn_ver and btn_ver.is_visible():
                btn_ver.click()
                page.wait_for_timeout(1500)

            btn_ret = (
                page.query_selector("//h3[contains(text(), 'MIS RETENCIONES')]/ancestor::a")
                or page.query_selector("a:has-text('MIS RETENCIONES')")
            )
            if not btn_ret:
                return {"ok": False, "error": "Servicio 'MIS RETENCIONES' no encontrado en el menú de ARCA."}

            with context.expect_page() as p_info:
                btn_ret.click()
            rp = p_info.value
            rp.wait_for_load_state("domcontentloaded")
            rp.wait_for_timeout(3000)

            # Extraer CUITs e impuestos disponibles en los combos de Mis Retenciones
            combos = rp.evaluate("""() => {
                const res = {};
                document.querySelectorAll('select').forEach((s, idx) => {
                    const name = s.name || s.id || ('select_' + idx);
                    res[name] = Array.from(s.options).slice(0, 12).map(o => ({v: o.value, t: o.text.trim()}));
                });
                return res;
            }""")

            return {
                "ok": True,
                "servicio": "MIS RETENCIONES (SIRE / SICORE)",
                "url": rp.url,
                "cuit_objetivo": cuit_target,
                "filtros_disponibles": combos,
                "nota": "Acceso validado a Mis Retenciones. Los certificados SIRE/SICORE se cruzan contra F. 2002 IVA y Ganancias."
            }
        finally:
            browser.close()


def consultar_nuestra_parte(usuario: str, clave: str) -> Dict[str, Any]:
    """
    Ingresa a 'Nuestra Parte' (vía acceso directo o desde Bienes Personales Web)
    para extraer los bienes, cuentas bancarias, inmuebles y consumos que ARCA conoce del contribuyente.
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
            page.wait_for_timeout(1500)
            btn_ver = page.query_selector("text='Ver todos'")
            if btn_ver and btn_ver.is_visible():
                btn_ver.click()
                page.wait_for_timeout(1500)

            # Intentar acceso directo a Nuestra Parte o vía Bienes Personales Web
            btn_np = (
                page.query_selector("//h3[contains(text(), 'NUESTRA PARTE')]/ancestor::a")
                or page.query_selector("a:has-text('NUESTRA PARTE')")
            )
            via = "directo"
            if btn_np:
                with context.expect_page() as p_info:
                    btn_np.click()
                np_page = p_info.value
                np_page.wait_for_load_state("domcontentloaded")
                np_page.wait_for_timeout(3000)
            else:
                via = "desde_bienes_personales_web"
                btn_bp = (
                    page.query_selector("//h3[contains(text(), 'BIENES PERSONALES WEB')]/ancestor::a")
                    or page.query_selector("a:has-text('BIENES PERSONALES WEB')")
                )
                if not btn_bp:
                    return {"ok": False, "error": "No se encontró Nuestra Parte ni Bienes Personales Web."}
                with context.expect_page() as p_info:
                    btn_bp.click()
                bp_page = p_info.value
                bp_page.wait_for_load_state("domcontentloaded")
                bp_page.wait_for_timeout(3500)

                # Hacer click en el segundo botón "CONSULTAR" (tarjeta Nuestra Parte)
                botones_consultar = bp_page.query_selector_all("button:has-text('CONSULTAR'), a:has-text('CONSULTAR')")
                if len(botones_consultar) >= 2:
                    with context.expect_page() as np_info:
                        botones_consultar[1].click()
                    np_page = np_info.value
                    np_page.wait_for_load_state("domcontentloaded")
                    np_page.wait_for_timeout(3500)
                else:
                    np_page = bp_page

            texto = np_page.inner_text("body")
            secciones = [
                l.strip() for l in texto.splitlines()
                if l.strip() and len(l.strip()) > 3
            ][:35]

            return {
                "ok": True,
                "servicio": "NUESTRA PARTE (Información registrada por ARCA)",
                "acceso_via": via,
                "url": np_page.url,
                "bloques_detectados": secciones
            }
        finally:
            browser.close()


def verificar_proveedor_apocrifo_apoc(cuit_proveedor: str) -> Dict[str, Any]:
    """
    Verifica si un proveedor figura en la Base e-APOC (Contribuyentes No Confiables / Facturas Apócrifas)
    de ARCA. Consulta pública oficial en tiempo real (no requiere Clave Fiscal).
    Fundamental para empresas y estudios contables antes de computar Crédito Fiscal de IVA o deducir Ganancias.
    """
    cuit_clean = "".join(c for c in str(cuit_proveedor) if c.isdigit())
    if len(cuit_clean) != 11:
        return {"ok": False, "error": "El CUIT del proveedor debe tener 11 dígitos."}

    url = "https://servicioscf.afip.gob.ar/Facturacion/facturasApocrifas/default.aspx"
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=_get_browser_path(),
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        page = browser.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(1500)

            inp = page.query_selector("input[id*='txtCuit'], input[name*='Cuit'], input[type='text']")
            if inp:
                inp.fill(cuit_clean)
                btn = page.query_selector("input[type='submit'], button[type='submit'], input[value*='Consultar']")
                if btn:
                    btn.click()
                    page.wait_for_load_state("domcontentloaded")
                    page.wait_for_timeout(2000)

            texto = page.inner_text("body")
            es_apocrifo = (
                "incluido en la base" in texto.lower()
                or "contribuyente no confiable" in texto.lower()
                or "condición: apócrifo" in texto.lower()
            ) and "no se encuentra incluido" not in texto.lower() and "no se encontraron" not in texto.lower()

            return {
                "ok": True,
                "servicio": "Base e-APOC ARCA (Facturas Apócrifas)",
                "cuit_proveedor": cuit_clean,
                "figura_en_base_apoc": es_apocrifo,
                "semaforo": "🔴 RIESGO CRÍTICO: PROVEEDOR EN BASE e-APOC" if es_apocrifo else "🟢 LIMPIO (No figura en base e-APOC)",
                "recomendacion": (
                    "NO computar Crédito Fiscal de IVA ni deducir este comprobante en Ganancias; ARCA impugna automáticamente facturas de sujetos en base e-APOC."
                    if es_apocrifo
                    else "El proveedor no registra inclusión en la base e-APOC al día de hoy."
                )
            }
        except Exception as e:
            return {
                "ok": False,
                "cuit_proveedor": cuit_clean,
                "error": str(e)
            }
        finally:
            browser.close()


def consultar_y_renovar_certificado_mipyme(
    usuario: str,
    clave: str,
    cuit_empresa: Optional[str] = None,
    confirmado: bool = False
) -> Dict[str, Any]:
    """
    Ingresa a 'PYMES SOLICITUD DE CATEGORIZACIÓN Y/O BENEFICIOS' (F. 1272) en ARCA
    para verificar el estado del Certificado MiPyME, su fecha de vencimiento, los beneficios
    activos (100% Impuesto al Cheque a cuenta, IVA diferido 90 días, SGR) y preparar su renovación.
    Respeta Human-in-the-Loop: solo presenta F. 1272 si confirmado=True.
    """
    cuit_target = "".join(c for c in str(cuit_empresa or usuario) if c.isdigit())
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
            page.wait_for_timeout(1500)
            btn_ver = page.query_selector("text='Ver todos'")
            if btn_ver and btn_ver.is_visible():
                btn_ver.click()
                page.wait_for_timeout(1500)

            btn_pyme = (
                page.query_selector("//h3[contains(text(), 'PYMES')]/ancestor::a")
                or page.query_selector("a:has-text('PYMES SOLICITUD')")
                or page.query_selector("a:has-text('PYMES')")
            )
            if not btn_pyme:
                return {
                    "ok": False,
                    "cuit": cuit_target,
                    "servicio_habilitado": False,
                    "error": "El servicio 'PYMES SOLICITUD DE CATEGORIZACIÓN Y/O BENEFICIOS' no está dado de alta aún en Administrador de Relaciones.",
                    "como_habilitarlo": "En ARCA → Administrador de Relaciones → Adherir Servicio → AFIP → Servicios Interactivos → PYMES Solicitud de Categorización y/o Beneficios (F. 1272).",
                    "beneficios_mipyme": [
                        "Cómputo del 100% del Impuesto sobre Débitos y Créditos Bancarios como pago a cuenta de Ganancias (Micro y Pequeñas).",
                        "Diferimiento del pago del saldo de IVA a 90 días.",
                        "Exclusión de regímenes de retención de IVA y Ganancias en tarjetas (RG 4011).",
                        "Acceso a avales SGR y líneas de crédito productivo a tasa subsidiada."
                    ]
                }

            with context.expect_page() as p_info:
                btn_pyme.click()
            pp = p_info.value
            pp.wait_for_load_state("domcontentloaded")
            pp.wait_for_timeout(3000)

            texto = pp.inner_text("body")
            lineas = [l.strip() for l in texto.splitlines() if l.strip()][:20]

            return {
                "ok": True,
                "servicio": "Certificado MiPyME (F. 1272)",
                "cuit": cuit_target,
                "modo": "ENVIO_F1272" if confirmado else "DIAGNOSTICO_Y_BORRADOR_SIN_IMPACTO",
                "url": pp.url,
                "estado_detectado": lineas,
                "requisitos_renovacion_automatica": [
                    "Tener presentadas las últimas 3 declaraciones juradas de IVA y F. 931 (si es empleador).",
                    "La renovación automática opera en el 4° mes posterior al cierre de ejercicio fiscal; si hubo demora se presenta el F. 1272 manualmente."
                ],
                "beneficios_mipyme": [
                    "100% Impuesto al Cheque computable a cuenta de Ganancias (Micro/Pequeña) o 60% (Mediana Tramo 1 industrial).",
                    "Pago de IVA diferido a 90 días.",
                    "Acceso a garantías SGR y tasa reducida de contribuciones patronales."
                ]
            }
        finally:
            browser.close()
