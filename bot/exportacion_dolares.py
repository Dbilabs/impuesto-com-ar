"""
Módulo de Exportación de Servicios y Dólares BCRA (impuesto.com.ar)
Emisión de Factura E, cálculo del cupo anual de USD sin pesificar obligatoria (BCRA)
y conversión al tipo de cambio oficial del día con liquidación cambiaria.
"""

from typing import Dict, Any, Optional
import datetime

# Cupo de libre disponibilidad anual según normativa BCRA para personas humanas que exportan servicios
CUPO_ANUAL_USD_BCRA = 24000.0

def calcular_cupo_dolares_freelancer(
    cuit: str,
    dolares_ingresados_anio: float,
    nuevo_cobro_usd: float,
    cotizacion_oficial_bna: float = 1045.0
) -> Dict[str, Any]:
    """
    Calcula el cupo restante de dólares libres de liquidación forzosa en MULC según Com. A 7518 y afines.
    """
    total_acumulado = dolares_ingresados_anio + nuevo_cobro_usd
    cupo_disponible = max(0.0, CUPO_ANUAL_USD_BCRA - dolares_ingresados_anio)

    entra_en_cupo = nuevo_cobro_usd <= cupo_disponible
    excedente_a_pesificar = max(0.0, nuevo_cobro_usd - cupo_disponible)
    dolares_en_mano = min(nuevo_cobro_usd, cupo_disponible)
    pesos_por_excedente = excedente_a_pesificar * cotizacion_oficial_bna

    # Explicación simple (chico de 10 años)
    if entra_en_cupo:
        explicacion = (
            f"¡Buenas noticias! Los USD {nuevo_cobro_usd:,.2f} que te pagaron entran enteros en tu cuenta en dólares del banco argentino. "
            f"El Banco Central te deja guardar hasta USD {CUPO_ANUAL_USD_BCRA:,.2f} al año como si fuera tu alcancía en billetes verdes. "
            f"Te quedan todavía USD {cupo_disponible - nuevo_cobro_usd:,.2f} libres para este año."
        )
    else:
        explicacion = (
            f"Atención: Superaste el cupo anual libre de USD {CUPO_ANUAL_USD_BCRA:,.2f}. "
            f"Podés recibir USD {dolares_en_mano:,.2f} directamente en billete verde, pero el sobrante de USD {excedente_a_pesificar:,.2f} "
            f"el banco te lo va a transformar obligatoriamente a pesos al cambio oficial (${pesos_por_excedente:,.2f})."
        )

    return {
        "cuit": cuit,
        "cupo_anual_limite_usd": CUPO_ANUAL_USD_BCRA,
        "dolares_ingresados_previos": round(dolares_ingresados_anio, 2),
        "nuevo_cobro_usd": round(nuevo_cobro_usd, 2),
        "cupo_restante_despues_de_cobro": round(max(0.0, cupo_disponible - nuevo_cobro_usd), 2),
        "liquidacion_bancaria_estimada": {
            "dolares_acreditables_en_cuenta_usd": round(dolares_en_mano, 2),
            "dolares_a_pesificar_oficial": round(excedente_a_pesificar, 2),
            "pesos_estimados_a_recibir": round(pesos_por_excedente, 2),
            "cotizacion_bna_aplicada": cotizacion_oficial_bna
        },
        "explicacion_10_anios": explicacion,
        "documentacion_requerida_banco": [
            "Factura E oficial emitida en ARCA",
            "Formulario de liquidación de divisas de comercio exterior del banco",
            "Contrato o comprobante de transferencia (Wise, Deel, Stripe, banco exterior)"
        ]
    }
