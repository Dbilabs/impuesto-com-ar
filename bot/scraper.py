import os
import io
import csv
import zipfile
import logging
from typing import List, Dict, Any, Optional
from playwright.sync_api import sync_playwright
from .arca_errors import ArcaNoDisponible, LoginNoConfirmado, ClaveIncorrecta

logger = logging.getLogger("arca_scraper")

def _get_browser_path():
    browser_executable = os.environ.get("CHROME_PATH")
    if not browser_executable and os.path.exists("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
        browser_executable = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    return browser_executable

def _login_arca(page, usuario: str, clave: str):
    import time as _t
    usuario_clean = usuario.replace("-", "").strip()
    password_enviada = False
    try:
        page.goto("https://auth.afip.gob.ar/contribuyente_/login.xhtml", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("#F1\\:username", timeout=15000)
        page.fill("#F1\\:username", usuario_clean)
        page.click("#F1\\:btnSiguiente")
        page.wait_for_selector("#F1\\:password", timeout=15000)
        page.fill("#F1\\:password", clave)
        page.click("#F1\\:btnIngresar")
        password_enviada = True

        # Detección rápida de error de credenciales sin esperar 30s de timeout
        for _ in range(12):
            if "portalcf.cloud.afip.gob.ar" in page.url or "portalcf.cloud.arca.gob.ar" in page.url:
                break
            try:
                body_low = page.inner_text("body").lower()
                if "clave o usuario incorrecto" in body_low:
                    raise ClaveIncorrecta("CLAVE_FISCAL_INCORRECTA: ARCA informó 'Clave o usuario incorrecto' para este CUIT.")
                if "clave bloqueada" in body_low or "usuario bloqueado" in body_low:
                    raise ClaveIncorrecta("CLAVE_FISCAL_BLOQUEADA: ARCA informó que la Clave Fiscal está bloqueada.", bloqueada=True)
                if "cambio de clave" in body_low or "cambiar su clave" in body_low:
                    raise ClaveIncorrecta("CAMBIO DE CLAVE: ARCA exige cambiar la Clave Fiscal antes de continuar.", cambio_clave=True)
                if "captcha" in body_low or "no soy un robot" in body_low:
                    raise ClaveIncorrecta("CAPTCHA: ARCA solicitó verificación captcha en el login.", captcha=True)
            except ClaveIncorrecta:
                raise
            except Exception:
                pass
            error_box = page.query_selector(".alert-danger, #errorMsg, .ui-messages-error")
            if error_box and error_box.is_visible():
                err_txt = (error_box.inner_text() or "").strip()
                err_low = err_txt.lower()
                if any(k in err_low for k in ("incorrect", "inválid", "invalida", "bloquead", "captcha", "cambio de clave")):
                    raise ClaveIncorrecta(
                        f"CLAVE_FISCAL_INCORRECTA: {err_txt}",
                        bloqueada="bloquead" in err_low,
                        cambio_clave="cambio de clave" in err_low,
                        captcha="captcha" in err_low,
                    )
                raise LoginNoConfirmado(f"Error de autenticación en ARCA sin confirmación: {err_txt}")
            _t.sleep(1.2)

        if "portalcf.cloud." not in page.url:
            page.wait_for_url("**/portalcf.cloud.**", timeout=20000, wait_until="domcontentloaded")
    except (ArcaNoDisponible, LoginNoConfirmado, ClaveIncorrecta):
        raise
    except Exception as exc:
        if not password_enviada:
            raise ArcaNoDisponible(f"ARCA no disponible antes de enviar la contraseña: {exc}") from exc
        raise LoginNoConfirmado(f"Login enviado sin confirmación en portalcf: {exc}") from exc

    try:
        page.wait_for_selector("#buscadorInput", timeout=20000)
    except Exception:
        page.wait_for_load_state("domcontentloaded", timeout=15000)
    page.wait_for_timeout(1200)
    page.keyboard.press("Escape")

def listar_empresas_representadas(usuario: str, clave: str) -> List[Dict[str, str]]:
    """
    Lista todas las personas y empresas que el usuario tiene autorización para operar.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=_get_browser_path(),
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        page = browser.new_page()
        page.set_default_timeout(12000)
        page.set_default_navigation_timeout(25000)
        try:
            _login_arca(page, usuario, clave)
            page.wait_for_selector("text='Ver todos'", timeout=20000)
            page.click("text='Ver todos'")
            page.wait_for_timeout(2000)

            btn = page.query_selector("//h3[contains(text(), 'ADMINISTRADOR DE RELACIONES DE CLAVE FISCAL')]/ancestor::a") or page.query_selector("text='ADMINISTRADOR DE RELACIONES DE CLAVE FISCAL'")
            if not btn:
                raise RuntimeError("No se encontró el Administrador de Relaciones de Clave Fiscal.")

            with page.context.expect_page(timeout=20000) as p_info:
                btn.click()
            adm_page = p_info.value
            try:
                adm_page.wait_for_load_state("domcontentloaded", timeout=20000)
            except Exception:
                pass
            adm_page.wait_for_timeout(2000)

            options = adm_page.evaluate('''() => {
                const res = [];
                document.querySelectorAll('select option').forEach(opt => {
                    const t = opt.innerText.trim();
                    const m = t.match(/(.+?)\\[(\\d{2}-\\d{8}-\\d)\\]/);
                    if (m) res.push({ razon_social: m[1].trim(), cuit: m[2].trim() });
                });
                return res;
            }''')
            return options
        finally:
            browser.close()

def consultar_notificaciones_dfe(usuario: str, clave: str, cuit_objetivo: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Consulta las notificaciones del Domicilio Fiscal Electrónico (DFE) para el CUIT o para todos los representados.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=_get_browser_path(),
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        page = browser.new_page()
        page.set_default_timeout(12000)
        page.set_default_navigation_timeout(25000)
        try:
            _login_arca(page, usuario, clave)
            btn_dfe = None
            try:
                search = page.locator("#buscadorInput").first
                search.wait_for(state="visible", timeout=15000)
                search.click(force=True)
                search.fill("Domicilio Fiscal Electrónico")
                page.wait_for_timeout(1800)
                items = page.locator("[id^='rbt-menu-item-']")
                for i in range(items.count()):
                    if "domicilio fiscal" in items.nth(i).inner_text().lower():
                        btn_dfe = items.nth(i)
                        break
            except Exception:
                pass
            if not btn_dfe:
                try:
                    page.wait_for_selector("text='Ver todos'", timeout=15000)
                    page.click("text='Ver todos'")
                    page.wait_for_timeout(1500)
                except Exception:
                    pass
                btn_dfe = page.query_selector("//h3[contains(text(), 'DOMICILIO FISCAL ELECTRÓNICO')]/ancestor::a") or page.query_selector("text='DOMICILIO FISCAL ELECTRÓNICO'")
            if not btn_dfe:
                raise RuntimeError("No se encontró el servicio Domicilio Fiscal Electrónico.")

            with page.context.expect_page(timeout=20000) as p_info:
                btn_dfe.click()
            dfe_page = p_info.value
            try:
                dfe_page.wait_for_load_state("domcontentloaded", timeout=20000)
            except Exception:
                pass
            dfe_page.wait_for_timeout(2500)

            # Si se especificó cuit o queremos todos (P1-6 + R3: validar que el CUIT pedido realmente exista en el select)
            if cuit_objetivo:
                clean_target = "".join(ch for ch in str(cuit_objetivo) if ch.isdigit())
                if len(clean_target) != 11:
                    raise ValueError(f"CUIT objetivo inválido para DFE: {cuit_objetivo!r}")
                selected = dfe_page.evaluate(
                    """(target) => {
                        const selects = document.querySelectorAll('select');
                        if (!selects.length) return { hasSelect: false, matched: false };
                        for (const s of selects) {
                            for (const opt of s.options) {
                                if (opt.text.replace(/[^0-9]/g, '').includes(target)) {
                                    s.value = opt.value;
                                    s.dispatchEvent(new Event('change'));
                                    return { hasSelect: true, matched: true };
                                }
                            }
                        }
                        return { hasSelect: true, matched: false };
                    }""",
                    clean_target,
                )
                if selected and selected.get("hasSelect") and not selected.get("matched"):
                    raise RuntimeError(f"CUIT_NO_ENCONTRADO_EN_DFE: El CUIT {clean_target} no figura entre los representados disponibles en DFE.")
                dfe_page.wait_for_timeout(2000)

            # Extraer notificaciones de la tabla
            comunicaciones = dfe_page.evaluate('''() => {
                const rows = [];
                document.querySelectorAll('table tbody tr').forEach(tr => {
                    const cols = Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim());
                    if (cols.length >= 3 && !cols[0].includes('No hay comunicaciones')) {
                        rows.push({
                            fecha: cols[0] || '',
                            asunto: cols[1] || '',
                            organismo: cols[2] || '',
                            estado: cols[3] || ''
                        });
                    }
                });
                return rows;
            }''')
            return comunicaciones
        finally:
            browser.close()

def consultar_mis_comprobantes(cuit: str, usuario: str, clave: str, tipo: str, rango_fechas: str) -> List[Dict[str, Any]]:
    """
    Descarga y parsea comprobantes emitidos o recibidos de Mis Comprobantes.
    """
    cuit_clean = cuit.replace("-", "").strip()
    cuit_fmt = f"{cuit_clean[:2]}-{cuit_clean[2:10]}-{cuit_clean[10:]}" if len(cuit_clean) == 11 else cuit_clean

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=_get_browser_path(),
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            _login_arca(page, usuario, clave)
            # Abrir Mis Comprobantes usando buscador oficial (más confiable que 'Ver todos')
            btn_mc = None
            try:
                search = page.locator("#buscadorInput").first
                search.wait_for(state="visible", timeout=20000)
                search.click(force=True)
                search.fill("Mis Comprobantes")
                page.wait_for_timeout(1800)
                items = page.locator("[id^='rbt-menu-item-']")
                for i in range(items.count()):
                    if "mis comprobantes" in items.nth(i).inner_text().lower():
                        btn_mc = items.nth(i)
                        break
            except Exception:
                pass
            if not btn_mc:
                try:
                    page.wait_for_selector("text='Ver todos'", timeout=15000)
                    page.click("text='Ver todos'")
                    page.wait_for_timeout(2000)
                except Exception:
                    pass
                btn_mc = page.query_selector("//h3[contains(text(), 'MIS COMPROBANTES')]/ancestor::a") or page.query_selector("text='MIS COMPROBANTES'")
            if not btn_mc:
                raise RuntimeError("No se encontró el servicio 'Mis Comprobantes' habilitado en este CUIT.")

            with page.context.expect_page(timeout=20000) as new_page_info:
                btn_mc.click()
            comp_page = new_page_info.value
            try:
                comp_page.wait_for_load_state("domcontentloaded", timeout=20000)
            except Exception:
                pass
            comp_page.wait_for_timeout(2500)

            btn_cuit = comp_page.query_selector(f"button:has-text('{cuit_fmt}')") or comp_page.query_selector(f"text='{cuit_fmt}'") or comp_page.query_selector(f"button:has-text('{cuit_clean}')")
            if btn_cuit:
                btn_cuit.click()
                try:
                    comp_page.wait_for_load_state("domcontentloaded", timeout=15000)
                except Exception:
                    pass
                comp_page.wait_for_timeout(2000)

            sub_url = (
                "https://fes.afip.gob.ar/mcmp/jsp/comprobantesEmitidos.do"
                if tipo.upper() == "E"
                else "https://fes.afip.gob.ar/mcmp/jsp/comprobantesRecibidos.do"
            )
            comp_page.goto(sub_url, wait_until="domcontentloaded", timeout=25000)
            comp_page.wait_for_timeout(2000)

            has_input = comp_page.query_selector("#fechaEmision")
            if not has_input:
                logger.warning(f"No se encontró el formulario de búsqueda de comprobantes para CUIT {cuit}")
                return []

            if rango_fechas:
                comp_page.evaluate(
                    "(val) => { const el = document.getElementById('fechaEmision'); el.value = val; el.dispatchEvent(new Event('change', {bubbles:true})); }",
                    rango_fechas,
                )
            comp_page.click("#buscarComprobantes")
            try:
                comp_page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            comp_page.wait_for_timeout(3000)

            csv_btn = comp_page.query_selector("button:has-text('CSV'), a:has-text('CSV')")
            if not csv_btn:
                return []

            with comp_page.expect_download(timeout=15000) as download_info:
                csv_btn.click()
            download = download_info.value
            temp_path = f"/tmp/arca_dl_{os.getpid()}_{id(download)}.tmp"
            download.save_as(temp_path)
            with open(temp_path, "rb") as f:
                data = f.read()
            if os.path.exists(temp_path):
                os.remove(temp_path)

            csv_text = ""
            if zipfile.is_zipfile(io.BytesIO(data)):
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    for name in z.namelist():
                        raw = z.read(name)
                        try:
                            csv_text = raw.decode("utf-8-sig")
                        except UnicodeDecodeError:
                            csv_text = raw.decode("latin-1")
                        break
            else:
                try:
                    csv_text = data.decode("utf-8-sig")
                except UnicodeDecodeError:
                    csv_text = data.decode("latin-1")

            if not csv_text.strip():
                return []

            lines = csv_text.splitlines()
            delim = ";" if (lines and lines[0].count(";") >= lines[0].count(",")) else ","
            reader = csv.DictReader(lines, delimiter=delim)
            rows = []
            for r in reader:
                clean_row = {k.strip(): (v.strip() if v else "") for k, v in r.items() if k}
                rows.append(clean_row)

            return rows

        finally:
            browser.close()
