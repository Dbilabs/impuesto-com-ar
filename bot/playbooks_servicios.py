"""
bot/playbooks_servicios.py
Protocolo Universal de Inicio (Pre-Flight) y Playbooks Operativos por Servicio Tributario.

Principio arquitectónico de impuesto.com.ar:
En ARCA, AGIP, ARBA, SIFERE y demás organismos fiscales, los valores reales casi NUNCA
aparecen por defecto al loguearse. Antes de operar o leer cualquier servicio, el agente
DEBE consultar su Playbook de Inicio (o ejecutar el Protocolo Pre-Flight de 6 preguntas)
para saber exactamente qué dropdown seleccionar, qué fechas pedir, qué botón dispara el
cálculo, si hay paginación, iframes o inputs ocultos, y qué módulos hermanos cruzar.
"""

from typing import Dict, Any, List, Optional

PROTOCOLO_PREFLIGHT_UNIVERSAL: List[Dict[str, str]] = [
    {
        "paso": "1. Identidad y Representado Activo",
        "pregunta": "¿Qué CUIT / Razón Social / Establecimiento está seleccionado por defecto?",
        "regla": "Nunca asumir que el primer ítem de un <select> es el contribuyente buscado. Leer el encabezado y seleccionar siempre por label/texto exacto de la CUIT."
    },
    {
        "paso": "2. Disparador de Consulta o Cálculo",
        "pregunta": "¿Los datos vienen precargados o hay que apretar un botón ('Cálculo de Deuda', 'Consultar', 'Siguiente', 'Filtrar')?",
        "regla": "Una pantalla vacía al entrar NO significa saldo $0 ni ausencia de registros: verificar siempre qué acción dispara la carga."
    },
    {
        "paso": "3. Ruta Real vs. Pantalla de Bienvenida",
        "pregunta": "¿La home (#/inicio) muestra el historial real o solo borradores / accesos?",
        "regla": "Navegar siempre a la pestaña de historial/presentaciones/seguimiento (ej: #/declaraciones.anteriores, #/declaracion.presentadas, Seguimiento de Presentación)."
    },
    {
        "paso": "4. Rangos de Fecha, Filtros y Paginación",
        "pregunta": "¿Qué rango de fechas, límite de períodos o páginas ('Mostrar 12/48', 'Página 1 de N', tope 1 año) está recortando la vista?",
        "regla": "Expandir el máximo de períodos o iterar año por año y recorrer TODAS las páginas antes de sumar totales."
    },
    {
        "paso": "5. Extracción Técnica del DOM",
        "pregunta": "¿Los importes están en texto plano, dentro de <input>.value, en un <iframe>, detrás de un modal o en un PDF en nueva pestaña?",
        "regla": "Leer tanto innerText como input.value, inspeccionar iframes, cerrar modales bloqueantes y capturar descargas/pestañas nuevas."
    },
    {
        "paso": "6. Cruce con Módulos Hermanos / Regímenes Paralelos",
        "pregunta": "¿Existe otro módulo que compensa, pone en cero o reemplaza lo que muestra esta pantalla?",
        "regla": "Ejemplo: Mis Facilidades pone en $0 CCMA/SCT ('Crédito por PFP'); F. 2711 Simplificada deja F. 711 como pendiente; AGIP/ARBA/SIFERE no figuran en ARCA."
    },
    {
        "paso": "7. Popups, Ventanas Emergentes y Pestañas Nuevas",
        "pregunta": "¿El servicio, comprobante PDF, VEP o acuse se abre en un popup/pestaña nueva (window.open / target='_blank')?",
        "regla": "Habilitar siempre ventanas emergentes (popups) para el dominio del organismo y escuchar eventos 'popup' / 'page' del navegador antes de hacer clic; si el popup está bloqueado, el servicio o comprobante falla en silencio."
    }
]

PLAYBOOKS_SERVICIOS: Dict[str, Dict[str, Any]] = {
    "arca_sct": {
        "organismo": "ARCA",
        "servicio": "Sistema de Cuentas Tributarias (SCT)",
        "como_inicia": "Entrar vía Portal CF o SSO directo (system=cuenta_corriente_contrib). En el panel izquierdo hay un <select> con todas las CUITs representadas.",
        "pasos_obligatorios": [
            "1. Seleccionar la CUIT exacta por label en el <select> y pulsar 'FILTRAR' (verificar nombre en cabecera).",
            "2. Ir a Cuenta Corriente > Estado de Cumplimiento: ingresar rango en formato AAAAMM00 (MÁXIMO 1 AÑO por consulta, ej. 20250000 a 20260000) y pulsar 'Siguiente'.",
            "3. Revisar también 'Detalle de Deuda Consolidada' y 'Detalle de Incumplimientos' (usar click JS si el menú lateral queda fuera del viewport).",
            "4. Para saldos a favor, recordar que cada período muestra su S.L.D. de origen (revisar año actual y año anterior)."
        ],
        "que_NO_muestra": "NO muestra deudas de Monotributo ni Autónomos (ver CCMA) ni cuotas futuras de planes de Mis Facilidades.",
        "aliases": ["sct", "cuentas tributarias", "sistema de cuentas tributarias"]
    },
    "arca_ccma": {
        "organismo": "ARCA",
        "servicio": "CCMA (Cuenta Corriente de Monotributistas y Autónomos)",
        "como_inicia": "Abrir desde el buscador del Portal CF ('CCMA'). La pantalla inicial es solo un formulario de 'Recálculo de Deuda a Fecha'.",
        "pasos_obligatorios": [
            "1. Pulsar 'Cálculo de Deuda' para disparar el cálculo actualizado a hoy.",
            "2. Leer el cuadro superior: Total Saldo Deudor, Obligación Mensual (capital), Accesorios (intereses resarcitorios) y Total Saldo Acreedor.",
            "3. Verificar 'Filtro Avanzado' (períodos desde/hasta, Mostrar 48 períodos, Todos los impuestos: 020, 021, 024, AUT).",
            "4. Si aparecen asientos 'Crédito por PFP Mis Facilidades Nro ...', ir OBLIGATORIAMENTE a Mis Facilidades."
        ],
        "que_NO_muestra": "No muestra impuestos generales DGI (Ganancias/IVA/BBPP) ni el saldo remanente de los planes de pago ya consolidados.",
        "aliases": ["ccma", "autonomos", "cuenta corriente monotributo"]
    },
    "arca_mis_facilidades": {
        "organismo": "ARCA",
        "servicio": "Mis Facilidades (Planes de Pago)",
        "como_inicia": "Abrir desde Portal CF ('Mis Facilidades'). Primero muestra un <select> con las CUITs asociadas (persona y sociedades).",
        "pasos_obligatorios": [
            "1. Seleccionar la CUIT exacta en <select> y confirmar ingreso.",
            "2. Ir a 'Seguimiento de Presentación' (carga por defecto o vía botón Consultar/Buscar) para listar TODOS los planes.",
            "3. Registrar Número, Régimen (RG 5321, RG 5629, RG 5711, Ley 27.653, Ley 27.743), Cuotas, Monto Consolidado y Situación (Vigente / Caduco / Cancelado).",
            "4. Para planes Vigentes, abrir 'Detalle / Impresiones / Cuotas' si se necesita saber cuotas impagas o riesgo de caducidad."
        ],
        "que_NO_muestra": "No incluye obligaciones corrientes no regularizadas (ver CCMA y SCT).",
        "aliases": ["mis facilidades", "planes de pago", "plan de facilidades", "moratoria"]
    },
    "arca_portal_monotributo": {
        "organismo": "ARCA",
        "servicio": "Portal Monotributo (admin_mono)",
        "como_inicia": "Abrir desde Portal CF o SSO (system=admin_mono). Muestra tarjeta de Categoría, Facturación acumulada vs Tope, Próximo vencimiento y Estado de Cuenta.",
        "pasos_obligatorios": [
            "1. Leer Categoría actual, Facturación electrónica acumulada y Tope de categoría (margen para próxima recategorización).",
            "2. Revisar tarjetas de 'Pagar período vencido' y 'Estado de Cuenta' (VER SALDO / PAGAR).",
            "3. Verificar si tiene Monotributo Unificado (AGIP/ARBA) o exclusión provincial."
        ],
        "que_NO_muestra": "No muestra deuda de Autónomos ni planes de pago antiguos (cruzar con CCMA y Mis Facilidades).",
        "aliases": ["monotributo", "portal monotributo", "admin_mono", "recategorizacion"]
    },
    "arca_ganancias_ph": {
        "organismo": "ARCA",
        "servicio": "Ganancias Personas Humanas (Portal Integrado: F. 711 + F. 2711 Simplificada)",
        "como_inicia": "Abrir 'Ganancias Personas Humanas - Portal Integrado' (gph/). Muestra DOS aplicativos distintos: 'Declaración Jurada' (F. 711) y 'Declaración Jurada Simplificada' (F. 2711 - RG 5692).",
        "pasos_obligatorios": [
            "1. SIEMPRE revisar ambos: primero 'Declaración Jurada Simplificada' (F. 2711) -> CONSULTAR (#/declaracion.presentadas) y verificar 'Ratificación anual'.",
            "2. Luego 'Declaración Jurada' (F. 711) -> CONTINUAR -> #/declaraciones.anteriores.",
            "3. En F. 2711, abrir menú '⋮' -> 'Ver DJ' -> 'Determinación' -> leer los <input>.value (los importes NO están en innerText).",
            "4. En F. 711, abrir 'Ver DJ' -> ingresar por los botones DECLARAR/INGRESAR de cada tarjeta (no clickear el título)."
        ],
        "que_NO_muestra": "F. 711 muestra vencido un período que ya fue presentado en F. 2711. Siempre cruzar ambos.",
        "aliases": ["ganancias", "f711", "f2711", "simplificada", "gph"]
    },
    "arca_bienes_personales": {
        "organismo": "ARCA",
        "servicio": "Bienes Personales Web (F. 762)",
        "como_inicia": "Abrir 'Bienes Personales Web'. La pantalla #/inicio solo muestra el año vigente o borradores.",
        "pasos_obligatorios": [
            "1. Navegar OBLIGATORIAMENTE a #/declaraciones.anteriores para ver el historial completo.",
            "2. Abrir 'Detalle de declaración jurada' de la última presentación y relevar bienes gravados, exentos, casa habitación, efectivo y determinación.",
            "3. Cruzar contra 'Nuestra Parte' del 31/12 correspondiente."
        ],
        "que_NO_muestra": "En #/inicio puede parecer sin presentaciones aunque existan más de 10 años presentados.",
        "aliases": ["bienes personales", "bbpp", "f762", "762"]
    },
    "agip_caba": {
        "organismo": "AGIP (CABA)",
        "servicio": "Cuenta Corriente Tributaria (CCMA/ISIB/ABL/Patentes - Clave Ciudad)",
        "como_inicia": "Login con Clave Ciudad (CUIT + clave). Seleccionar el servicio específico: 'Cuenta Corriente Tributaria', 'e-SICOL' (IIBB Local) o 'Nueva Cuenta Corriente Tributaria'.",
        "pasos_obligatorios": [
            "1. Verificar el impuesto/inscripción en el selector (IIBB Local, Régimen Simplificado, Agente de Recaudación, ABL, Patentes).",
            "2. Disparar 'Consultar Estado de Cuenta' / 'Deuda Total' seleccionando TODOS los períodos (no solo el año en curso).",
            "3. Revisar pestaña de 'Planes de Facilidades' y 'Deuda en Gestión Judicial / Mandatarios' (no siempre suma en cuenta corriente administrativa)."
        ],
        "que_NO_muestra": "No incluye impuestos nacionales (ARCA) ni otras provincias.",
        "aliases": ["agip", "caba", "clave ciudad", "isib", "esicol"]
    },
    "arba_pba": {
        "organismo": "ARBA (Provincia de Buenos Aires)",
        "servicio": "Autogestión / Cuenta Corriente IIBB, Inmobiliario y Automotor (CIT)",
        "como_inicia": "Login con CIT (Clave de Identificación Tributaria). Seleccionar tipo de impuesto (Ingresos Brutos, Inmobiliario, Automotores, Agentes).",
        "pasos_obligatorios": [
            "1. Seleccionar objeto imponible / N° de inscripción o partida.",
            "2. Consultar 'Estado de Deuda' y 'Presentaciones de DDJJ' (verificar falta de presentación aunque deuda diga $0).",
            "3. Revisar 'Planes de Pago' vigentes/caducos y 'Deuda en Apremio / Prejudicial'."
        ],
        "que_NO_muestra": "No incluye deuda nacional (ARCA) ni tasas municipales bonaerenses (TISH).",
        "aliases": ["arba", "pba", "provincia de buenos aires", "cit"]
    },
    "sifere_cm": {
        "organismo": "Comisión Arbitral (COMARB)",
        "servicio": "SIFERE Web (Convenio Multilateral - CM03 / CM05)",
        "como_inicia": "Se ingresa a través de ARCA con Clave Fiscal ('Convenio Multilateral - SIFERE WEB - DDJJ' y 'SIFERE WEB - Consultas').",
        "pasos_obligatorios": [
            "1. Seleccionar CUIT representada y jurisdicción sede.",
            "2. Revisar DDJJ mensuales (CM03) y anual (CM05) presentadas y pagadas por cada jurisdicción adherida.",
            "3. Cruzar retenciones bancarias (SIRCREB) y tarjetas (SIRTAC) para detectar saldos a favor inmovilizados."
        ],
        "que_NO_muestra": "Cada provincia liquida intereses y multas en su propio fisco; verificar cuentas corrientes locales si hay mora.",
        "aliases": ["sifere", "convenio multilateral", "comarb", "cm03", "cm05", "sircreb"]
    }
}


def obtener_playbook_servicio(servicio_o_consulta: str) -> Dict[str, Any]:
    """
    Devuelve el Playbook de Inicio (cómo se inicia, qué dropdowns/fechas/botones requiere,
    qué trampas tiene y qué NO muestra) para un servicio de ARCA u otro organismo tributario,
    junto con el Protocolo Pre-Flight Universal de 6 preguntas obligatorias.
    """
    q = (servicio_o_consulta or "").lower().strip()
    if q in PLAYBOOKS_SERVICIOS:
        pb = PLAYBOOKS_SERVICIOS[q]
        return {
            "servicio_encontrado": True,
            "id": q,
            "playbook": pb,
            "protocolo_preflight_universal": PROTOCOLO_PREFLIGHT_UNIVERSAL
        }

    for k, pb in PLAYBOOKS_SERVICIOS.items():
        if any(al in q for al in pb.get("aliases", [])) or k in q:
            return {
                "servicio_encontrado": True,
                "id": k,
                "playbook": pb,
                "protocolo_preflight_universal": PROTOCOLO_PREFLIGHT_UNIVERSAL
            }

    return {
        "servicio_encontrado": False,
        "consulta": servicio_o_consulta,
        "servicios_con_playbook_verificado": list(PLAYBOOKS_SERVICIOS.keys()),
        "instruccion_obligatoria": (
            "Este servicio aún no tiene un playbook específico cargado. ANTES de reportar cualquier valor "
            "o saldo $0, ejecutá obligatoriamente las 6 preguntas del protocolo_preflight_universal "
            "e inspeccioná el manual oficial del organismo."
        ),
        "protocolo_preflight_universal": PROTOCOLO_PREFLIGHT_UNIVERSAL
    }
