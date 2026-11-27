import os
import re
import logging
from typing import Dict, Any, List, Optional
from playwright.sync_api import sync_playwright

logger = logging.getLogger("arca_monotributo")

def _get_browser_path():
    browser_executable = os.environ.get("CHROME_PATH")
    if not browser_executable and os.path.exists("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
        browser_executable = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    return browser_executable

def _login_arca(page, usuario: str, clave: str):
    usuario_clean = usuario.replace("-", "").strip()
    page.goto("https://auth.afip.gob.ar/contribuyente_/login.xhtml", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector("#F1\\:username", timeout=15000)
    page.fill("#F1\\:username", usuario_clean)
    page.click("#F1\\:btnSiguiente")
    page.wait_for_selector("#F1\\:password", timeout=15000)
    page.fill("#F1\\:password", clave)
    page.click("#F1\\:btnIngresar")
    page.wait_for_timeout(3000)

    error_box = page.query_selector(".alert-danger, #errorMsg, .ui-messages-error")
    if error_box and error_box.is_visible():
        err_txt = error_box.inner_text()
        raise ValueError(f"Error de autenticación en ARCA: {err_txt}")

def consultar_estado_monotributo(usuario: str, clave: str) -> Dict[str, Any]:
    """
    Ingresa al portal oficial de MONOTRIBUTO en ARCA y extrae en vivo:
    - Nombre del contribuyente y CUIT
    - Categoría actual y tipo de actividad (Servicios / Bienes)
    - Facturación acumulada anual y tope de la categoría actual
    - Próximo vencimiento e importe de cuota
    - Períodos vencidos pendientes de pago
    - Próximo período de recategorización
    """
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
            page.wait_for_selector("text='Ver todos'", timeout=20000)
            page.click("text='Ver todos'")
            page.wait_for_timeout(2000)

            # Localizar el card de Monotributo
            mono_btn = page.query_selector('a[title="admin_mono"]') or page.query_selector("text='MONOTRIBUTO'")
            if not mono_btn:
                raise RuntimeError("El servicio MONOTRIBUTO no se encuentra en el portal de clave fiscal.")

            with page.context.expect_page(timeout=20000) as p_info:
                mono_btn.click()
            mono_page = p_info.value
            try:
                mono_page.wait_for_load_state("domcontentloaded", timeout=20000)
            except Exception:
                pass
            mono_page.wait_for_timeout(3500)

            body_text = mono_page.inner_text("body")

            # Parsear datos clave con regex y extracción semántica
            # 1. Contribuyente
            nombre_match = re.search(r'V\s*\d+\.\d+\.\d+\.\d+\s+Inicio\s+([A-ZÁÉÍÓÚÑ\s]+?)\s+CUIT\s+([\d\-]+)', body_text)
            nombre = nombre_match.group(1).strip() if nombre_match else "No detectado"
            cuit_detectado = nombre_match.group(2).strip() if nombre_match else usuario

            # 2. Categoria
            cat_match = re.search(r'Categoría\s+([A-K])\s+(.+?)(?=\n|Próximo)', body_text)
            categoria = cat_match.group(1).strip() if cat_match else "Desconocida"
            tipo_actividad = cat_match.group(2).strip() if cat_match else ""

            # 3. Proximo periodo recategorizacion
            reca_match = re.search(r'Próximo período de recategorización:\s*([A-Za-z]+\s+\d{4})', body_text)
            proxima_recat = reca_match.group(1).strip() if reca_match else ""

            # 4. Facturación y topes
            fact_match = re.search(r'\$([\d\.]+,\d{2})\s+Monto facturado', body_text)
            monto_facturado_str = fact_match.group(1).strip() if fact_match else "0,00"

            tope_match = re.search(r'\$([\d\.]+,\d{2})\s+Tope categoría', body_text)
            tope_cat_str = tope_match.group(1).strip() if tope_match else "0,00"

            # 5. Próximo vencimiento
            venc_match = re.search(r'Tu próximo vencimiento es el\s+([\d\-a-z]+)\s+y el importe a pagar es\s+\$([\d\.]+,\d{2})', body_text, re.IGNORECASE)
            proximo_vencimiento = venc_match.group(1).strip() if venc_match else ""
            cuota_proxima_str = venc_match.group(2).strip() if venc_match else "0,00"

            # 6. Deuda o período vencido
            deuda_match = re.search(r'Pagar período vencido \'([^\']+)\'', body_text)
            periodo_vencido = deuda_match.group(1).strip() if deuda_match else None

            # Conversiones numéricas
            def _clean_num(val_str: str) -> float:
                try:
                    return float(val_str.replace(".", "").replace(",", "."))
                except Exception:
                    return 0.0

            monto_facturado = _clean_num(monto_facturado_str)
            tope_cat = _clean_num(tope_cat_str)
            cuota_proxima = _clean_num(cuota_proxima_str)

            margen_disponible = max(0.0, tope_cat - monto_facturado)
            porcentaje_uso = round((monto_facturado / tope_cat * 100), 2) if tope_cat > 0 else 0.0

            return {
                "contribuyente": nombre,
                "cuit": cuit_detectado,
                "categoria_actual": categoria,
                "tipo_actividad": tipo_actividad,
                "facturacion_anual": monto_facturado,
                "facturacion_anual_fmt": f"${monto_facturado:,.2f}",
                "tope_categoria": tope_cat,
                "tope_categoria_fmt": f"${tope_cat:,.2f}",
                "margen_disponible": margen_disponible,
                "margen_disponible_fmt": f"${margen_disponible:,.2f}",
                "porcentaje_uso_categoria": f"{porcentaje_uso}%",
                "proxima_recategorizacion": proxima_recat,
                "proximo_vencimiento": proximo_vencimiento,
                "cuota_proxima": cuota_proxima,
                "cuota_proxima_fmt": f"${cuota_proxima:,.2f}",
                "periodo_vencido_pendiente": periodo_vencido,
                "alerta_deuda": True if periodo_vencido else False
            }
        finally:
            browser.close()

def generar_plan_de_accion(datos_monotributo: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Construye el Plan de Acción con Bots ejecutores listos para dispararse.
    """
    plan = []

    # 1. Bot de Pago / VEP si hay deuda
    if datos_monotributo.get("alerta_deuda"):
        periodo = datos_monotributo["periodo_vencido_pendiente"]
        plan.append({
            "id": "bot_pago_cuota_vencida",
            "titulo": f"Regularizar cuota vencida ({periodo})",
            "tipo": "FINANCIERO_FISCAL",
            "prioridad": "ALTA",
            "descripcion": f"Se detectó la cuota de {periodo} pendiente en ARCA. Evita intereses resarcitorios y corte de obra social.",
            "bot_ejecutor": {
                "nombre": "bot_monotributo_generar_vep",
                "parametros": {"periodo": periodo, "medio_pago": "QR_INTERBANKING"},
                "confirmacion_requerida": True,
                "boton_texto": f"Generar VEP / QR para {periodo}"
            }
        })

    # 2. Bot de Recategorización según margen
    pct_str = datos_monotributo.get("porcentaje_uso_categoria", "0%").replace("%", "")
    pct = float(pct_str) if pct_str else 0.0

    if pct >= 80.0:
        plan.append({
            "id": "bot_recategorizacion_alerta",
            "titulo": f"Proyección y Simulación de Recategorización ({datos_monotributo.get('proxima_recategorizacion')})",
            "tipo": "CATEGORIZACION",
            "prioridad": "MEDIA" if pct < 90 else "URGENTE",
            "descripcion": f"Tu facturación consumió el {pct}% del tope de Categoría {datos_monotributo.get('categoria_actual')}. Te quedan sólo {datos_monotributo.get('margen_disponible_fmt')} de margen.",
            "bot_ejecutor": {
                "nombre": "bot_monotributo_simular_recategorizacion",
                "parametros": {
                    "categoria_actual": datos_monotributo.get("categoria_actual"),
                    "facturacion_anual": datos_monotributo.get("facturacion_anual")
                },
                "confirmacion_requerida": False,
                "boton_texto": "Simular Próxima Categoría y Nueva Cuota"
            }
        })

    # 3. Bot de Descarga de Credencial
    plan.append({
        "id": "bot_descarga_credencial",
        "titulo": "Descargar Credencial de Pago (F. 152)",
        "tipo": "ADMINISTRATIVO",
        "prioridad": "BAJA",
        "descripcion": "Descarga la constancia oficial de Monotributo y credencial de pago con código de barras y CUR.",
        "bot_ejecutor": {
            "nombre": "bot_monotributo_descargar_credencial",
            "parametros": {"cuit": datos_monotributo.get("cuit")},
            "confirmacion_requerida": False,
            "boton_texto": "Obtener Credencial PDF"
        }
    })

    # 4. Trámites Registrales (Alta / Baja / Modificación)
    plan.append({
        "id": "bot_tramite_registral",
        "titulo": "Modificación de Datos o Baja de Régimen",
        "tipo": "REGISTRAL",
        "prioridad": "DISPONIBLE",
        "descripcion": "Gestión de cese de actividad, cambio de domicilio fiscal, alta de nueva actividad económica o baja definitiva.",
        "bot_ejecutor": {
            "nombre": "bot_monotributo_modificacion_baja",
            "opciones": ["BAJA_CESE_ACTIVIDAD", "CAMBIO_ACTIVIDAD", "MODIFICAR_DOMICILIO"],
            "confirmacion_requerida": True,
            "boton_texto": "Iniciar Trámite Registral"
        }
    })

    return plan
