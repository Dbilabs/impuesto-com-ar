"""
Módulo de Recordatorios Fiscales y Manejo de Contingencias ARCA (impuesto.com.ar)
Calcula fechas exactas de vencimientos según terminación de CUIT y régimen (Monotributo / RI / Empleador)
y provee sugerencias de reintento automático cuando ARCA experimenta caídas de servicio.
"""

import datetime
from typing import Dict, Any, List, Optional

def calcular_vencimientos_cuit(cuit: str, regimen: str = "auto") -> Dict[str, Any]:
    """
    Calcula los vencimientos oficiales de ARCA para el mes en curso y el próximo
    según la terminación del CUIT.
    """
    cuit_clean = cuit.replace("-", "").strip()
    terminacion = int(cuit_clean[-1]) if cuit_clean and cuit_clean[-1].isdigit() else 0
    now = datetime.date.today()
    mes_actual = now.strftime("%B %Y")

    # Matriz oficial de días según terminación de CUIT (ARCA)
    # IVA F. 2002 / Libro IVA Digital: terminación 0-1 (día 18), 2-3 (día 19), 4-5 (día 20), 6-7 (día 21), 8-9 (día 22)
    dia_iva = 18 + (terminacion // 2)
    
    # Cargas Sociales F. 931 (Empleadores): terminación 0-1-2-3 (día 9), 4-5-6 (día 10), 7-8-9 (día 11)
    if terminacion <= 3:
        dia_f931 = 9
    elif terminacion <= 6:
        dia_f931 = 10
    else:
        dia_f931 = 11

    # Monotributo: vence habitualmente el día 20 de cada mes
    dia_mono = 20

    # Próxima recategorización semestral
    if now.month <= 6:
        proxima_recat = "01/07/2026 al 20/07/2026 (Semestre 1)"
    else:
        proxima_recat = "01/01/2027 al 20/01/2027 (Semestre 2)"

    recordatorios = []

    # Recordatorios Monotributo
    if regimen.lower() in ["auto", "monotributo"]:
        recordatorios.append({
            "id": "rec_mono_mensual",
            "titulo": f"Pago Cuota Mensual Monotributo ({now.strftime('%m/%Y')})",
            "fecha_limite": f"{dia_mono:02d}/{now.month:02d}/{now.year}",
            "frecuencia": "Mensual (día 20)",
            "accion_recomendada": "Generar VEP o QR de pago antes del vencimiento para evitar intereses.",
            "prompt_sugerido": f"Recordame el día {dia_mono - 2} pagar la cuota del Monotributo con el QR de ARCA."
        })
        recordatorios.append({
            "id": "rec_mono_recategorizacion",
            "titulo": "Recategorización Semestral Obligatoria",
            "periodo": proxima_recat,
            "frecuencia": "Semestral (Enero y Julio)",
            "accion_recomendada": "Revisar facturación acumulada últimos 12 meses y confirmar categoría.",
            "prompt_sugerido": "Avisame en Enero para auditar mi facturación y recategorizarme."
        })

    # Recordatorios Empresas / Responsables Inscriptos
    if regimen.lower() in ["auto", "empresa", "responsable inscripto", "ri"]:
        recordatorios.append({
            "id": "rec_iva_f2002",
            "titulo": f"Presentación DDJJ IVA F. 2002 y Cierre Libro IVA Digital ({now.strftime('%m/%Y')})",
            "fecha_limite": f"{dia_iva:02d}/{now.month:02d}/{now.year}",
            "frecuencia": f"Mensual (día {dia_iva} por terminación {terminacion})",
            "accion_recomendada": "Cerrar compras y ventas en el Portal IVA y generar la presentación oficial.",
            "prompt_sugerido": f"Recordame el día {dia_iva - 2} revisar el borrador del F. 2002 de IVA y confirmarlo."
        })
        recordatorios.append({
            "id": "rec_f931_cargas_sociales",
            "titulo": f"Cargas Sociales F. 931 - Empleadores ({now.strftime('%m/%Y')})",
            "fecha_limite": f"{dia_f931:02d}/{now.month:02d}/{now.year}",
            "frecuencia": f"Mensual (día {dia_f931} por terminación {terminacion})",
            "accion_recomendada": "Declaración jurada y generación de VEP de aportes y contribuciones de seguridad social.",
            "prompt_sugerido": f"Recordame el día {dia_f931 - 1} revisar las cargas sociales de nómina."
        })

    return {
        "cuit": cuit,
        "terminacion": terminacion,
        "regimen_detectado": regimen,
        "recordatorios_predeterminados": recordatorios
    }

def generar_respuesta_arca_caida(operacion: str, cuit: str, detalle_error: str) -> Dict[str, Any]:
    """
    Genera una respuesta inteligente cuando los servidores de ARCA devuelven timeout o error 500/503.
    """
    now = datetime.datetime.now()
    reintento_1 = (now + datetime.timedelta(hours=2)).strftime("%H:%M hs")
    reintento_2 = "mañana a las 09:00 hs"

    return {
        "estado": "ARCA_TEMPORALMENTE_NO_DISPONIBLE",
        "operacion_interrumpida": operacion,
        "cuit": cuit,
        "diagnostico": "Los servidores de ARCA (ex-AFIP) no respondieron a tiempo o están en mantenimiento programado. Tu trámite y tus datos NO se perdieron.",
        "detalle_tecnico": detalle_error[:200],
        "acciones_sugeridas": [
            {
                "opcion": "Reintentar en 2 horas",
                "horario": reintento_1,
                "comando_ia": f"Recordame en 2 horas volver a intentar {operacion} en ARCA."
            },
            {
                "opcion": "Reintentar mañana a primera hora",
                "horario": reintento_2,
                "comando_ia": f"Recordame mañana a las 9 am ejecutar {operacion} en ARCA."
            }
        ],
        "instruccion_para_ia": "Informale al usuario con tranquilidad que ARCA suele saturarse en horarios pico, y ofrecete a agendarle un recordatorio para reintentar la operación automáticamente en el horario sugerido."
    }
