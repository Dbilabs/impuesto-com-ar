"""
Módulo de Ingresos Brutos y Convenio Multilateral (impuesto.com.ar)
Calcula la base imponible y el impuesto para regímenes locales (AGIP, ARBA)
y Convenio Multilateral (SIFERE Web CM03), auditando retenciones bancarias SIRCREB.
"""

from typing import Dict, Any, List, Optional

# Alícuotas de referencia habituales en Ingresos Brutos
ALICUOTAS_IIBB_REFERENCIA = {
    "servicios_caba": 0.03,        # 3% AGIP Servicios
    "comercio_caba": 0.03,         # 3% AGIP Comercio
    "servicios_pba": 0.035,        # 3.5% ARBA Servicios
    "comercio_pba": 0.035,         # 3.5% ARBA Comercio
    "industria": 0.015,            # 1.5% Industria general
    "profesionales_caba": 0.0      # 0% Profesionales universitarios exentos en CABA
}

def liquidar_iibb_periodo(
    cuit: str,
    periodo: str,
    jurisdiccion: str, # "CABA", "PBA" o "CONVENIO_MULTILATERAL"
    facturacion_bruta: float,
    alicuota: float = 0.03,
    retenciones_bancarias_sircreb: float = 0.0,
    percepciones_sufridas: float = 0.0,
    saldo_a_favor_anterior: float = 0.0,
    coeficientes_cm: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """
    Calcula la posición mensual de Ingresos Brutos y alerta sobre retenciones bancarias excesivas.
    """
    juris = jurisdiccion.upper()

    if "CONVENIO" in juris:
        # Convenio Multilateral SIFERE CM03: distribución por coeficientes
        coefs = coeficientes_cm or {"CABA (901)": 0.60, "Buenos Aires (902)": 0.40}
        detalle_juris = []
        impuesto_determinado_total = 0.0

        for nombre_j, coef in coefs.items():
            base_j = facturacion_bruta * coef
            imp_j = base_j * alicuota
            impuesto_determinado_total += imp_j
            detalle_juris.append({
                "jurisdiccion": nombre_j,
                "coeficiente": coef,
                "base_imponible": round(base_j, 2),
                "alicuota": f"{alicuota * 100:.1f}%",
                "impuesto_determinado": round(imp_j, 2)
            })
    else:
        # Jurisdicción local única (ej. AGIP o ARBA)
        impuesto_determinado_total = facturacion_bruta * alicuota
        detalle_juris = [{
            "jurisdiccion": juris,
            "coeficiente": 1.0,
            "base_imponible": round(facturacion_bruta, 2),
            "alicuota": f"{alicuota * 100:.1f}%",
            "impuesto_determinado": round(impuesto_determinado_total, 2)
        }]

    # Deducción de pagos a cuenta
    total_deducciones = retenciones_bancarias_sircreb + percepciones_sufridas + saldo_a_favor_anterior
    diferencia = impuesto_determinado_total - total_deducciones

    if diferencia > 0:
        saldo_a_pagar = diferencia
        nuevo_saldo_a_favor = 0.0
    else:
        saldo_a_pagar = 0.0
        nuevo_saldo_a_favor = abs(diferencia)

    # Detección de alerta SIRCREB (si el banco te sacó más del 100% del impuesto de tu mes)
    alerta_retencion_abusiva = False
    if retenciones_bancarias_sircreb > impuesto_determinado_total and impuesto_determinado_total > 0:
        alerta_retencion_abusiva = True

    # Explicación simple (chico de 10 años)
    if alerta_retencion_abusiva:
        explicacion_simple = f"¡Cuidado! El banco te sacó ${retenciones_bancarias_sircreb:,.2f} en mordidas automáticas (SIRCREB), que es más de lo que tenías que pagar de impuesto (${impuesto_determinado_total:,.2f}). La plata no se perdió: te quedó a favor (${nuevo_saldo_a_favor:,.2f}), pero te conviene pedir un certificado de reducción para que el banco no te muerda tanto la cuenta cada vez que te transfieren."
    elif saldo_a_pagar > 0:
        explicacion_simple = f"De todo lo que facturaste (${facturacion_bruta:,.2f}), a la provincia le corresponde su tajada del {alicuota*100:.1f}%. Como tus retenciones fueron de ${total_deducciones:,.2f}, te queda pagar una diferencia de ${saldo_a_pagar:,.2f}."
    else:
        explicacion_simple = f"No tenés que pagar nada de Ingresos Brutos este mes. Tus retenciones y saldo anterior cubrieron todo, y te sobraron ${nuevo_saldo_a_favor:,.2f} para el próximo mes."

    return {
        "periodo": periodo,
        "cuit": cuit,
        "tipo_regimen": "Convenio Multilateral (SIFERE CM03)" if "CONVENIO" in juris else f"Régimen Local ({juris})",
        "facturacion_bruta_total": round(facturacion_bruta, 2),
        "detalle_por_provincia": detalle_juris,
        "liquidacion": {
            "impuesto_determinado": round(impuesto_determinado_total, 2),
            "retenciones_bancarias_sircreb": round(retenciones_bancarias_sircreb, 2),
            "percepciones_sufridas": round(percepciones_sufridas, 2),
            "saldo_a_favor_anterior": round(saldo_a_favor_anterior, 2),
            "total_pagos_a_cuenta": round(total_deducciones, 2),
            "saldo_a_pagar": round(saldo_a_pagar, 2),
            "nuevo_saldo_a_favor": round(nuevo_saldo_a_favor, 2),
            "estado": "A PAGAR" if saldo_a_pagar > 0 else "SALDO A FAVOR"
        },
        "alerta_sircreb_abusivo": alerta_retencion_abusiva,
        "explicacion_sencilla": explicacion_simple
    }
