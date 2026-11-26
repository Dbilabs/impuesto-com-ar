"""
Módulo de Liquidación de Sueldos y Cargas Sociales F. 931 (impuesto.com.ar)
Calcula el sueldo neto de empleados, aportes de seguridad social (17%) y contribuciones
patronales de la empresa para armar el Formulario 931 y Libro de Sueldos Digital.
"""

from typing import Dict, Any, List

def liquidar_sueldo_y_cargas(
    sueldo_bruto: float,
    tipo_empleador: str = "servicios", # "servicios" o "comercio_industria" (Decreto 814 / Ley 27.541)
    alicuota_art: float = 0.035,        # ART promedio 3.5%
    seguro_vida_obligatorio: float = 850.0
) -> Dict[str, Any]:
    """
    Calcula el recibo de sueldo de un empleado y el costo total empresa para el F. 931.
    """
    # 1. Descuentos al empleado (Aportes del trabajador = 17%)
    jubilacion_11 = sueldo_bruto * 0.11
    ley_19032_pami = sueldo_bruto * 0.03
    obra_social_3 = sueldo_bruto * 0.03
    total_descuentos_empleado = jubilacion_11 + ley_19032_pami + obra_social_3
    sueldo_neto_en_mano = sueldo_bruto - total_descuentos_empleado

    # 2. Contribuciones a cargo de la empresa (Contribuciones patronales)
    # Alícuota SIPA / PAMI / Asignaciones / FNE según tipo de empleador
    tasa_patronal = 0.204 if "serv" in tipo_empleador.lower() else 0.18
    contribucion_seguridad_social = sueldo_bruto * tasa_patronal
    contribucion_obra_social = sueldo_bruto * 0.06 # 6% patronal a obra social
    art_laboral = sueldo_bruto * alicuota_art
    total_contribuciones_empresa = contribucion_seguridad_social + contribucion_obra_social + art_laboral + seguro_vida_obligatorio

    # 3. Total a pagar a ARCA por este empleado en el Formulario 931
    total_f931_vep = total_descuentos_empleado + total_contribuciones_empresa
    costo_total_empleador = sueldo_bruto + total_contribuciones_empresa

    # Explicación simple (chico de 10 años)
    explicacion_simple = (
        f"Imaginá que el empleado pactó un sueldo de ${sueldo_bruto:,.2f}. "
        f"A él le llegan en mano ${sueldo_neto_en_mano:,.2f}, porque por ley se guardan ${total_descuentos_empleado:,.2f} para su jubilación y médico. "
        f"Pero a vos como dueño de la empresa no te cuesta solo eso: tenés que poner de tu bolsillo ${total_contribuciones_empresa:,.2f} extra de cargas sociales y seguro. "
        f"En total, para pagarle a este empleado tenés que desembolsar ${costo_total_empleador:,.2f}, y a fin de mes le pagás a ARCA un VEP de F. 931 por ${total_f931_vep:,.2f}."
    )

    return {
        "sueldo_bruto": round(sueldo_bruto, 2),
        "recibo_sueldo_empleado": {
            "sueldo_bruto": round(sueldo_bruto, 2),
            "descuento_jubilacion_11": round(jubilacion_11, 2),
            "descuento_pami_3": round(ley_19032_pami, 2),
            "descuento_obra_social_3": round(obra_social_3, 2),
            "total_retenciones_empleado": round(total_descuentos_empleado, 2),
            "sueldo_neto_a_cobrar": round(sueldo_neto_en_mano, 2)
        },
        "cargas_patronales_empresa": {
            "seguridad_social_patronal": round(contribucion_seguridad_social, 2),
            "obra_social_patronal_6": round(contribucion_obra_social, 2),
            "art_seguro_accidentes": round(art_laboral, 2),
            "seguro_vida": round(seguro_vida_obligatorio, 2),
            "total_cargas_patronales": round(total_contribuciones_empresa, 2)
        },
        "formulario_931_arca": {
            "aportes_retenidos": round(total_descuentos_empleado, 2),
            "contribuciones_empresa": round(total_contribuciones_empresa, 2),
            "total_vep_f931": round(total_f931_vep, 2),
            "costo_laboral_total": round(costo_total_empleador, 2)
        },
        "explicacion_sencilla": explicacion_simple
    }
