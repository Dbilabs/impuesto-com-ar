"""
bot/crawler_manuales_arca.py
Crawler y Motor de Ingesta de Manuales, Guías Paso a Paso y Micrositios de ARCA (ex-AFIP).
Descarga, estructura e indexa el conocimiento oficial de trámites (vigentes e históricos)
para entrenar a la IA con los flujos de pantallas, solapas, selectores y lógica tributaria.
"""

import os
import sys
import re
import json
import ssl
import urllib.request
from html import unescape
from typing import Dict, Any, List

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "manuales_arca"))
os.makedirs(DATA_DIR, exist_ok=True)
INDEX_FILE = os.path.join(DATA_DIR, "indice_guias_arca.json")

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

MICROSITIOS_BASE = [
    {"nombre": "Portal de Guías Oficiales", "url": "https://www.afip.gob.ar/guias/", "categoria": "GENERAL"},
    {"nombre": "Monotributo", "url": "https://www.afip.gob.ar/monotributo/default.asp", "categoria": "MONOTRIBUTO"},
    {"nombre": "Ganancias y Bienes Personales", "url": "https://www.afip.gob.ar/gananciasybienes/", "categoria": "GANANCIAS_Y_BIENES"},
    {"nombre": "Clave Fiscal", "url": "https://www.afip.gob.ar/clavefiscal/", "categoria": "CLAVE_FISCAL"},
    {"nombre": "Presentaciones Digitales", "url": "https://www.afip.gob.ar/Presentaciones-Digitales/", "categoria": "TRAMITES_DIGITALES"},
    {"nombre": "Autónomos", "url": "https://www.afip.gob.ar/autonomos/default.asp", "categoria": "AUTONOMOS"},
    {"nombre": "Cómo Pagar Impuestos (VEP y CBU)", "url": "https://www.afip.gob.ar/comopagarimpuestos/", "categoria": "PAGOS_Y_VEP"},
    {"nombre": "Aplicativos Históricos y SiAP", "url": "https://www.afip.gob.ar/Aplicativos/default.asp", "categoria": "APLICATIVOS_HISTORICOS"}
]

def fetch_url(url: str, timeout: int = 15) -> str:
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=CTX, timeout=timeout) as resp:
            data = resp.read()
            # Intentar decodificar utf-8 o latin1
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError:
                return data.decode("latin1", errors="ignore")
    except Exception as e:
        print(f"⚠️ Error al conectar a {url}: {e}")
        return ""

def extraer_guias_portal():
    print("▶ 1. Extrayendo catálogo de guías desde https://www.afip.gob.ar/guias/ ...")
    html = fetch_url("https://www.afip.gob.ar/guias/")
    if not html:
        return []

    # Extraer enlaces a guías
    matches = re.findall(r"<a\s+[^>]*href=[\"\x27]([^\"\x27]+)[\"\x27][^>]*>(.*?)</a>", html, re.DOTALL)
    guias_encontradas = []

    for href, texto in matches:
        t_clean = re.sub(r"<[^>]+>", " ", texto).strip()
        t_clean = re.sub(r"\s+", " ", t_clean)
        t_clean = unescape(t_clean)

        if not t_clean or len(t_clean) < 8:
            continue

        h_lower = href.lower()
        if any(k in h_lower for k in ["verguia", "guiaspasopaso", "paso-a-paso", "manual", "guiadetramites", ".pdf"]):
            # Normalizar URL
            if href.startswith("/"):
                url_completa = "https://www.afip.gob.ar" + href
            elif not href.startswith("http"):
                url_completa = "https://www.afip.gob.ar/guias/" + href
            else:
                url_completa = href

            # Determinar categoría y estado
            categoria = "GENERAL"
            t_upper = t_clean.upper()
            if any(k in t_upper for k in ["MONOTRIBUTO", "RECATEGORIZACION", "CATEGORIA"]):
                categoria = "MONOTRIBUTO"
            elif any(k in t_upper for k in ["BIENES PERSONALES", "GANANCIAS", "F. 762", "762"]):
                categoria = "GANANCIAS_Y_BIENES"
            elif any(k in t_upper for k in ["FACTURA", "COMPROBANTE", "RCEL", "PUNTO DE VENTA"]):
                categoria = "FACTURACION"
            elif any(k in t_upper for k in ["IVA", "F. 2002", "LIBRO DE IVA DIGITAL"]):
                categoria = "IVA"
            elif any(k in t_upper for k in ["SUELDO", "931", "EMPLEADO", "EMPLEADOR", "LSD"]):
                categoria = "SUELDOS_Y_SEGURIDAD_SOCIAL"
            elif any(k in t_upper for k in ["CLAVE FISCAL", "DELEGACION", "ADMINISTRADOR"]):
                categoria = "CLAVE_FISCAL"
            elif any(k in t_upper for k in ["CBU", "VEP", "PAGO", "DEBITO"]):
                categoria = "PAGOS"

            es_obsoleto = any(k in t_upper for k in ["SIAP", "APLICATIVO", "HISTORICO", "DISQUETE", "VERSION 1."])

            guias_encontradas.append({
                "titulo": t_clean,
                "url": url_completa,
                "categoria": categoria,
                "estado_vigencia": "historico_logica_base" if es_obsoleto else "vigente",
                "tipo": "pdf" if ".pdf" in h_lower else "guia_web"
            })

    # Deduplicar por URL
    unicas = []
    urls_vistas = set()
    for g in guias_encontradas:
        if g["url"] not in urls_vistas:
            urls_vistas.add(g["url"])
            unicas.append(g)

    print(f"✓ {len(unicas)} guías oficiales indexadas desde el portal.")
    return unicas

def incorporar_conocimiento_clave_arca(guias: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Sintetiza la lógica operativa y pantallas de los trámites más críticos de ARCA
    (incluyendo los detalles de sub-solapas como #/declaraciones.anteriores de F. 762).
    """
    conocimiento_servicios = {
        "BIENES_PERSONALES_WEB_F762": {
            "nombre": "Bienes Personales Web (Formulario 762)",
            "url_base": "https://siapweb.cloud.afip.gob.ar/f762/",
            "tecnologia": "Single Page Application (SPA AngularJS con SAML Auth)",
            "rutas_internas_criticas": {
                "#/inicio": "Pantalla de bienvenida y alerta de próximo vencimiento anual.",
                "#/declaraciones.anteriores": "SOLAPA VITAL: Contiene el historial completo de declaraciones juradas presentadas desde 2013 hasta la fecha.",
                "#/crearDJ": "Asistente para iniciar nueva DDJJ determinativa o informativa seleccionando el año fiscal.",
                "#/bienes": "Carga de inmuebles, automotores, dinero en efectivo, cuentas bancarias y participaciones sociales."
            },
            "reglas_de_negocio": [
                "Las cuotas de SRL o acciones de SA se declaran bajo 'Acciones y Participaciones Societarias Art. 25.1' y son NO COMPUTABLES (alícuota 0%) en cabeza del socio porque las ingresa la empresa como Responsable Sustituto con F. 8115.",
                "Cajas de ahorro en pesos y dólares y plazos fijos están 100% EXENTOS por el Art. 21 de la Ley 23.966.",
                "Mínimo No Imponible Ley 27.743: $100.000.000 general, y $350.000.000 para casa habitación."
            ],
            "logica_historica": "Reemplazó al viejo aplicativo SiAP 'Bienes Personales'. Mantiene idénticos conceptos de valuación fiscal de inmuebles y tablas de automotores."
        },
        "FACTURACION_COMPROBANTES_EN_LINEA_RCEL": {
            "nombre": "Comprobantes en Línea (RCEL)",
            "url_base": "https://fe.afip.gob.ar/rcel/",
            "tecnologia": "Java Web legacy con popups y selección de empresa representada",
            "rutas_internas_criticas": {
                "empresa_representada": "Primer paso obligatorio: elegir si se opera como persona humana o para una sociedad representada.",
                "punto_de_venta": "Paso 2: Elegir Punto de Venta electrónico habilitado (Tipo 'Factura Electrónica - Monotributo' o 'Factura Electrónica - Web Services').",
                "datos_comprobante": "Paso 3: Concepto (Servicios, Productos o ambos). Período facturado y vencimiento del pago.",
                "datos_receptor": "Paso 4: CUIT del cliente. El sistema consulta el padrón en línea y auto-completa la Razón Social.",
                "emision_final": "Paso 5: Resumen previo. Tras presionar 'Confirmar', ARCA asigna el CAE (Código de Autorización Electrónico) y el Código QR."
            },
            "logica_historica": "El servicio utiliza llamadas AJAX ('actualizarDescripcionPVConDelay') que requieren esperar el refresh antes de seleccionar la letra del comprobante."
        },
        "IVA_F2002_Y_LIBRO_DIGITAL": {
            "nombre": "Declaración Jurada de IVA (F. 2002) y Libro de IVA Digital",
            "url_base": "https://iva.afip.gob.ar/",
            "tecnologia": "Portal IVA y Aplicativo F. 2002 Web",
            "rutas_internas_criticas": {
                "libro_iva_digital": "RG 4597: Importación de comprobantes de ventas y compras emitidos en el mes.",
                "f2002_debito_credito": "Cálculo del Débito Fiscal menos Crédito Fiscal.",
                "saldos_primer_parrafo": "Saldo técnico a favor de ARCA o del contribuyente (Art. 24 primer párrafo Ley de IVA).",
                "saldos_segundo_parrafo": "Saldo de Libre Disponibilidad por retenciones y percepciones bancarias (Art. 24 segundo párrafo)."
            },
            "logica_historica": "Reemplazó al Régimen Informativo de Compras y Ventas (CITI Ventas / CITI Compras). Exige cerrar primero el Libro Digital para poder habilitar la presentación del F. 2002."
        },
        "MONOTRIBUTO_PORTAL": {
            "nombre": "Portal Oficial de Monotributo",
            "url_base": "https://monotributo.afip.gob.ar/",
            "rutas_internas_criticas": {
                "admin_mono": "Ficha del contribuyente: categoría actual, facturación acumulada 12 meses y límite de escala.",
                "recategorizacion": "Habilitado en Enero y Julio para evaluar ingresos de los últimos 12 meses.",
                "pagos": "Generación de VEP / QR interoperable para pago en bancos o billeteras virtuales."
            }
        }
    }

    base_completa = {
        "version_base": "2026.1.0",
        "descripcion": "Base de conocimiento operacional de ARCA / AFIP: manuales oficiales, flujos de SPA y lógica tributaria.",
        "total_guias_oficiales_indexadas": len(guias),
        "guias_oficiales": guias,
        "manuales_operativos_servicios": conocimiento_servicios
    }

    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(base_completa, f, indent=2, ensure_ascii=False)

    print(f"✓ Base de conocimiento guardada en: {INDEX_FILE}")
    return base_completa

if __name__ == "__main__":
    guias = extraer_guias_portal()
    incorporar_conocimiento_clave_arca(guias)
