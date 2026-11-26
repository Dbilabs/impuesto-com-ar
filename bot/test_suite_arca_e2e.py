"""
bot/test_suite_arca_e2e.py
Suite de Diagnóstico End-to-End (100% lectura / dry-run) sobre todos los servicios críticos de ARCA.
Objetivo: verificar que cada bot funcione sin errores en 1 contribuyente + empresa representada
ANTES de escalar a modo cartera de 100+ clientes para estudios contables.

Servicios evaluados:
1. WSFEv1 (FEDummy Web Service oficial)
2. Login + Administrador de Relaciones (listar_empresas_representadas)
3. Mis Comprobantes (Emitidos y Recibidos para la empresa)
4. Domicilio Fiscal Electrónico (DFE para titular y empresa)
5. Portal Monotributo (admin_mono: categoría, tope, margen, deuda)
6. Bienes Personales Web (F. 762 #/declaraciones.anteriores)
7. Comprobantes en Línea (RCEL: selección de empresa + PV AJAX + tipos habilitados, sin emitir)
8. Presentación de DDJJ y Pagos (con auto-cierre de modal bloqueante)
"""

import os
import sys
import time
import json
import traceback
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from bot.arca_ws import verificar_estado_servidores_wsfe
from bot.scraper import (
    _get_browser_path,
    _login_arca,
    listar_empresas_representadas,
    consultar_mis_comprobantes,
    consultar_notificaciones_dfe
)
from bot.scraper_monotributo import consultar_estado_monotributo
from bot.scraper_bbpp import consultar_bienes_personales_web

USUARIO = os.environ.get("ARCA_TEST_CUIT", "")
CLAVE = os.environ.get("ARCA_TEST_CLAVE", "")
CUIT_EMPRESA = os.environ.get("ARCA_TEST_CUIT_EMPRESA", "")
RAZON_EMPRESA = os.environ.get("ARCA_TEST_RAZON_EMPRESA", "MI EMPRESA S.R.L.")


def test_rcel_dry_run():
    """Verifica acceso a RCEL para la empresa, PV AJAX y tipos habilitados (sin emitir)."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=_get_browser_path(),
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        context = browser.new_context()
        page = context.new_page()
        try:
            _login_arca(page, USUARIO, CLAVE)
            page.wait_for_timeout(1500)
            btn_ver = page.query_selector("text='Ver todos'")
            if btn_ver and btn_ver.is_visible():
                btn_ver.click()
                page.wait_for_timeout(1500)

            btn_rcel = (
                page.query_selector("//h3[contains(text(), 'COMPROBANTES EN LÍNEA')]/ancestor::a")
                or page.query_selector("a:has-text('COMPROBANTES EN LÍNEA')")
            )
            if not btn_rcel:
                raise RuntimeError("No se encontró 'COMPROBANTES EN LÍNEA' en el menú.")

            with context.expect_page() as p_info:
                btn_rcel.click()
            rcel = p_info.value
            rcel.wait_for_load_state("networkidle")
            rcel.wait_for_timeout(1500)

            btn_emp = rcel.query_selector(f"input[value*='{RAZON_EMPRESA}']") or rcel.query_selector(f"text='{RAZON_EMPRESA}'")
            if not btn_emp:
                raise RuntimeError(f"No se encontró el botón de empresa {RAZON_EMPRESA} en RCEL.")
            btn_emp.click()
            rcel.wait_for_load_state("networkidle")
            rcel.wait_for_timeout(1500)

            btn_gen = rcel.query_selector("a:has-text('Generar Comprobantes')") or rcel.query_selector("#btn_gen_cmp")
            if not btn_gen:
                raise RuntimeError("No se encontró 'Generar Comprobantes' en RCEL.")
            btn_gen.click()
            rcel.wait_for_load_state("networkidle")
            rcel.wait_for_timeout(1500)

            # Seleccionar primer PV válido y disparar AJAX
            pvs = rcel.evaluate("""() => {
                const s = document.querySelector("#puntodeventa");
                if (!s) return [];
                const opts = Array.from(s.options).filter(o => o.value && o.value !== "");
                if (opts.length > 0) {
                    s.value = opts[0].value;
                    s.dispatchEvent(new Event("change"));
                    if (typeof ajaxFunction === "function") ajaxFunction();
                }
                return opts.map(o => o.text.trim());
            }""")
            rcel.wait_for_timeout(2000)

            tipos = rcel.evaluate("""() => {
                const s = document.querySelector("#universocomprobante");
                if (!s) return [];
                return Array.from(s.options).filter(o => o.value && o.value !== "").map(o => o.text.trim());
            }""")
            return {"puntos_venta": pvs, "tipos_habilitados": tipos}
        finally:
            browser.close()


def test_presentacion_ddjj_con_modal():
    """Verifica ingreso a 'PRESENTACIÓN DE DDJJ Y PAGOS' cerrando el modal bloqueante."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=_get_browser_path(),
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        context = browser.new_context()
        page = context.new_page()
        try:
            _login_arca(page, USUARIO, CLAVE)
            page.wait_for_timeout(1500)
            btn_ver = page.query_selector("text='Ver todos'")
            if btn_ver and btn_ver.is_visible():
                btn_ver.click()
                page.wait_for_timeout(1500)

            btn_ddjj = (
                page.query_selector("//h3[contains(text(), 'PRESENTACIÓN DE DDJJ Y PAGOS')]/ancestor::a")
                or page.query_selector("a:has-text('PRESENTACIÓN DE DDJJ Y PAGOS')")
            )
            if not btn_ddjj:
                raise RuntimeError("No se encontró 'PRESENTACIÓN DE DDJJ Y PAGOS'.")

            with context.expect_page() as p_info:
                btn_ddjj.click()
            dp = p_info.value
            dp.wait_for_load_state("networkidle")
            dp.wait_for_timeout(2500)

            # Cerrar cualquier modal Bootstrap bloqueante (.modal.fade.show)
            modal_cerrado = dp.evaluate("""() => {
                const modal = document.querySelector('.modal.fade.show, div[role="dialog"].show');
                if (!modal) return false;
                const btn = modal.querySelector('button.close, button[data-dismiss="modal"], button:not([disabled])');
                if (btn) { btn.click(); return true; }
                modal.remove();
                document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());
                return true;
            }""")
            dp.wait_for_timeout(1000)

            # Intentar click en "Presentaciones" ahora sin modal
            card_pres = dp.query_selector("text='Presentaciones'")
            if card_pres:
                card_pres.click(force=True)
                dp.wait_for_timeout(2000)

            return {
                "modal_detectado_y_cerrado": modal_cerrado,
                "url_actual": dp.url,
                "titulo_visible": dp.inner_text("body")[:180].replace("\n", " | ")
            }
        finally:
            browser.close()


def run_suite():
    tests = [
        ("1. WSFEv1 (Web Service Oficial)", lambda: verificar_estado_servidores_wsfe("produccion")),
        ("2. Administrador de Relaciones (Empresas)", lambda: listar_empresas_representadas(USUARIO, CLAVE)),
        ("3. Mis Comprobantes (Empresa Recibidos)", lambda: consultar_mis_comprobantes(CUIT_EMPRESA, USUARIO, CLAVE, tipo="R", rango_fechas="01/10/2026 - 25/11/2026")),
        ("4. Domicilio Fiscal Electrónico (DFE)", lambda: consultar_notificaciones_dfe(USUARIO, CLAVE)),
        ("5. Portal Monotributo (admin_mono)", lambda: consultar_estado_monotributo(USUARIO, CLAVE)),
        ("6. Bienes Personales Web (F. 762)", lambda: consultar_bienes_personales_web(USUARIO, CLAVE)),
        ("7. Comprobantes en Línea (RCEL Dry-Run)", test_rcel_dry_run),
        ("8. Presentación DDJJ y Pagos (Fix Modal)", test_presentacion_ddjj_con_modal),
    ]

    resultados = []
    print("=" * 72)
    print("🧪 SUITE END-TO-END DE ROBUSTEZ DE BOTS ARCA (MODO LECTURA / DRY-RUN)")
    print("=" * 72)

    for nombre, fn in tests:
        t0 = time.time()
        try:
            res = fn()
            dt = round(time.time() - t0, 1)
            ok = True
            if isinstance(res, dict) and res.get("online") is False:
                ok = False
            if isinstance(res, dict) and res.get("ok") is False:
                ok = False

            resumen = ""
            if isinstance(res, list):
                resumen = f"{len(res)} registros extraídos"
            elif isinstance(res, dict):
                if "total_presentaciones_historicas" in res:
                    resumen = f"{res['total_presentaciones_historicas']} DDJJs históricas (última: {res['ultimo_periodo_presentado']})"
                elif "categoria" in res:
                    resumen = f"Cat {res.get('categoria')} | Facturado: {res.get('facturado_12m')}"
                elif "tipos_habilitados" in res:
                    resumen = f"PVs: {len(res['puntos_venta'])} | Tipos: {len(res['tipos_habilitados'])}"
                elif "AppServer" in res:
                    resumen = f"App={res['AppServer']} Db={res['DbServer']} Auth={res['AuthServer']}"
                elif "modal_detectado_y_cerrado" in res:
                    resumen = f"Modal cerrado={res['modal_detectado_y_cerrado']} | URL={res['url_actual'][:55]}"
                else:
                    resumen = str(list(res.keys())[:4])

            estado = "✅ PASS" if ok else "❌ FAIL"
            print(f"{estado} | {dt:4.1f}s | {nombre} -> {resumen}")
            resultados.append({"test": nombre, "ok": ok, "segundos": dt, "resumen": resumen})
        except Exception as e:
            dt = round(time.time() - t0, 1)
            print(f"❌ FAIL | {dt:4.1f}s | {nombre} -> ERROR: {e}")
            resultados.append({"test": nombre, "ok": False, "segundos": dt, "error": str(e)})

    passed = sum(1 for r in resultados if r["ok"])
    print("=" * 72)
    print(f"RESULTADO GLOBAL: {passed}/{len(resultados)} servicios PASS")
    print("=" * 72)
    with open("/tmp/arca_e2e_report.json", "w", encoding="utf-8") as f:
        json.dump(resultados, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    run_suite()
