"""
Cerebro de Asesoramiento Tributario y Planificación Fiscal (impuesto.com.ar)
Provee respuestas técnicas con citas a leyes argentinas pero explicadas con analogías
sencillas (estilo 'para un chico de 10 años') para que cualquier dueño de pyme o monotributista
entienda qué hacer con su plata sin marearse con términos jurídicos oscuros.
"""

from typing import Dict, Any, List

CONSEJOS_TRIBUTARIOS = {
    "que_gastos_deducir": {
        "titulo": "¿Qué gastos puedo pasar por la empresa o negocio para pagar menos impuestos?",
        "analogia_10_anios": "Imaginá que tenés un puesto de limonada. Si comprás limones, azúcar, vasos descartables y el cartelito con el precio, todo eso es necesario para vender limonada; se lo restás a tus ganancias y pagás menos impuesto. Pero si con la plata de la limonada te comprás una pelota de fútbol o ropa para ir a bailar, la maestra (ARCA) te va a decir: '¡Esa pelota no te ayuda a hacer limonada!', te anula el gasto y te cobra una multa.",
        "regla_fiscal_real": "Artículo 83 de la Ley de Impuesto a las Ganancias: Son deducibles todos los gastos necesarios para obtener, mantener y conservar la ganancia gravada. Gastos de uso personal o familiar (ropa común, supermercado familiar, viajes de placer) están expresamente prohibidos por el Art. 92 de la Ley.",
        "ejemplos_permitidos": [
            "Luz, internet y teléfono del lugar de trabajo",
            "Software, hosting, licencias y computadoras",
            "Combustible y seguro de utilitarios afectados al negocio",
            "Honorarios de profesionales, diseñadores y publicidad",
            "Insumos de oficina y mercadería de reventa"
        ],
        "ejemplos_peligrosos": [
            "Supermercado con comida de la casa",
            "Auto de alta gama a nombre personal sin justificación comercial",
            "Viajes de vacaciones pasados como 'congresos'"
        ]
    },
    "monotributo_vs_srl": {
        "titulo": "¿Cuándo me conviene pasar de Monotributo a una Sociedad (S.R.L. o S.A.S.)?",
        "analogia_10_anios": "El Monotributo es como una bicicleta: es barata, fácil de andar y pagás una cuota fija como Netflix. Pero si tu negocio empieza a transportar camiones llenos de cajas (mucha facturación), la bicicleta no aguanta más y te caés. Una S.R.L. es como un auto: cuesta más mantenerlo y hay que hacerle service todos los meses, pero si tenés un choque, tu casa y tus ahorros personales están a salvo porque la que responde es la empresa, no vos.",
        "regla_fiscal_real": "Régimen Simplificado (Ley 24.977) vs Régimen General (Ley de Sociedades 19.550). El Monotributo tiene tope anual (Cat K). Al superarlo, pasar como persona humana a Responsable Inscripto te hace pagar hasta el 35% de Ganancias sobre tu bolsillo personal. Una S.R.L. tributa tasa escalonada (25% al 35%), protege el patrimonio de los socios con responsabilidad limitada y permite deducir honorarios de directores.",
        "recomendacion_accion": "Si estás en Categoría H o I y proyectás seguir creciendo, es el momento exacto para armar la SRL antes de que ARCA te excluya de oficio a mitad de año con deudas retroactivas."
    },
    "saldo_a_favor_banco": {
        "titulo": "¿Por qué el banco me saca plata de mis transferencias (SIRCREB) y cómo la recupero?",
        "analogia_10_anios": "Imaginá que cada vez que un amigo te pasa 10 figuritas por recreo, viene el celador del colegio (el banco por orden de ARBA o AGIP) y se queda con 1 figurita antes de que la toques. Si al final del día la provincia te cobra 3 figuritas de impuesto pero el banco te sacó 10, te quedaron 7 figuritas atrapadas en la oficina del celador. Eso es el saldo a favor: plata tuya que el estado te retuvo de más.",
        "regla_fiscal_real": "Régimen de Recaudación y Control sobre Acreditaciones Bancarias (SIRCREB - Convenio Multilateral). Ocurre por alícuotas desfasadas en el padrón o falta de presentación de declaraciones juradas CM03.",
        "recomendacion_accion": "Presentamos el Bot de Exclusión de Retenciones (RG 2226 / trámite web en ARBA/AGIP) demostrando que tu saldo a favor supera 3 meses de impuesto para que la alícuota bancaria baje a 0%."
    },
    "retirar_plata_empresa": {
        "titulo": "¿Cómo saco plata de mi empresa sin pagar impuestos dos veces?",
        "analogia_10_anios": "Si la empresa ganó $100 y vos sos el dueño, no podés meter la mano en la caja y llevártelos a tu bolsillo como si fuera tu billetera, porque la ley dice que la empresa es una persona distinta a vos. Hay dos caminos legales para sacar la plata: 1) Pagarte un sueldo/honorario por trabajar de jefe (que la empresa puede restar como gasto), o 2) Esperar a fin de año, pagar el impuesto de la empresa y repartirte las ganancias (dividendos al 7%).",
        "regla_fiscal_real": "Honorarios al Directorio (Art. 91 inc. i Ley de Ganancias) hasta el límite del 25% de la utilidad contable o $12.500.000 (el mayor) son deducibles de Ganancias para la sociedad, y tributan en cabeza del director. Los dividendos tributan retención del 7% de impuesto cedular (Art. 97).",
        "recomendacion_accion": "Hacer una liquidación mixta: cobrar honorarios de director deducibles mes a mes hasta el tope de ley, y el remanente distribuirlo como dividendos aprobados por asamblea."
    }
}

def consultar_asesor(tema: str) -> Dict[str, Any]:
    """
    Devuelve la respuesta del Asesor Fiscal Inteligente con explicación dual:
    para chicos de 10 años + cita técnica para el contador.
    """
    t = tema.lower().strip()
    for k, v in CONSEJOS_TRIBUTARIOS.items():
        if k in t or any(w in t for w in k.split("_")):
            return v
            
    # Respuesta genérica si no coincide con una clave exacta
    return {
        "titulo": "Consulta impositiva general",
        "analogia_10_anios": "Los impuestos son como la cuota del club: todos los socios ponen un poquito para que haya pileta, luz y canchas de fútbol. El secreto no es esconder la plata, sino saber qué beneficios y descuentos te da el reglamento para no pagar ni un peso de más.",
        "regla_fiscal_real": "Principio de legalidad y capacidad contributiva (Constitución Nacional Art. 17). Toda obligación tributaria debe emanar de una ley formal y liquidarse sobre hechos imponibles reales.",
        "temas_populares": list(CONSEJOS_TRIBUTARIOS.keys())
    }
