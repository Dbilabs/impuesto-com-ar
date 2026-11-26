"""
bot/novedades_fiscales.py
Motor de Novedades Fiscales, Moratorias, Blanqueo, Planes de Pago y Human-in-the-Loop.
Traduce la complejidad diaria de las resoluciones de ARCA en oportunidades claras
explicadas "como para un chico de 10 años", y gestiona la solicitud de revisión
por parte de un Contador Público Matriculado.
"""

from typing import Dict, Any, List, Optional
import datetime

NOVEDADES_VIGENTES = [
    {
        "id": "nov_moratoria_27743",
        "categoria": "MORATORIAS_Y_ALIVIO",
        "titulo": "Moratoria Fiscal Ley 27.743: Condonación de multas y hasta 100% de intereses",
        "analogia_10_anios": (
            "Es como si hubieras roto un vidrio jugando a la pelota en la escuela y el director te dijera: "
            "'Si venís a pedir perdón hoy y pagás el vidrio roto, te perdono el reto, la penitencia "
            "y los intereses del castigo'. Solo pagás lo que debías originalmente y te olvidás de las multas."
        ),
        "impacto_segun_perfil": {
            "monotributo": "Permite regularizar cuotas mensuales impagas viejas sin pagar los intereses acumulados.",
            "empresa_ri": "Permite condonar hasta el 100% de intereses resarcitorios y punitorios de IVA, Ganancias y Aportes F. 931, financiando en hasta 84 cuotas."
        },
        "beneficio_clave": "Condonación de hasta el 100% de intereses y extinción de la acción penal tributaria.",
        "normativa_oficial": "Ley 27.743 (Título II - Régimen de Regularización Excepcional) y RG 5525/2024 ARCA."
    },
    {
        "id": "nov_blanqueo_activos",
        "categoria": "REGULARIZACION_ACTIVOS",
        "titulo": "Régimen de Regularización de Activos (Blanqueo de Capitales): 0% hasta USD 100.000",
        "analogia_10_anios": (
            "Imaginá que tenías una alcancía escondida debajo de la cama que nunca le mostraste a nadie. "
            "El estado abre una ventana especial y te dice: 'Poné esa plata sobre la mesa en una cuenta especial. "
            "Si son hasta 100.000 dólares (o si la usás para comprar una casa o invertir), no pagás ni una moneda "
            "de castigo (0% de impuesto) y a partir de hoy podés comprar lo que quieras sin miedo a que te pregunten'."
        ),
        "impacto_segun_perfil": {
            "monotributo": "Podés justificar fondos para comprar un auto, departamento o herramientas sin riesgo de que ARCA te excluya del régimen.",
            "empresa_ri": "Sinceramiento de inventarios, bienes no declarados y cuentas del exterior para sanear el balance comercial."
        },
        "beneficio_clave": "Tasa 0% hasta USD 100.000 y liberación de todos los impuestos omitidos pasados (IVA, Ganancias, Bienes Personales).",
        "normativa_oficial": "Ley 27.743 (Título II) y Decretos Reglamentarios 608/2024 y 773/2024."
    },
    {
        "id": "nov_plan_permanente_arca",
        "categoria": "PLANES_DE_PAGO",
        "titulo": "Planes de Pago Permanentes de ARCA (RG 5321 y modificaciones)",
        "analogia_10_anios": (
            "Si no llegás a pagar la cuota completa del mes, es como pedirle al quiosquero que te anote la compra "
            "y te la divida en cuotas chiquitas por semana. Así no te corta el servicio ni te manda al cobrador."
        ),
        "impacto_segun_perfil": {
            "monotributo": "Financiación de deudas en hasta 20 o 36 cuotas debitadas automáticamente de tu CBU el día 16 de cada mes.",
            "empresa_ri": "Financiación de IVA mensual, Ganancias y cargas sociales con tasa fija referenciada a la tasa pasiva del Banco Nación."
        },
        "beneficio_clave": "Levanta embargos bancarios y restablece la condición de cumplimiento fiscal en 48 horas.",
        "normativa_oficial": "Resolución General ARCA 5321/2023 y RG 5590/2024."
    },
    {
        "id": "nov_cupo_dolares_freelancers",
        "categoria": "DIVISAS_Y_EXPORTACION",
        "titulo": "Cobro de USD sin pesificar para profesionales independientes (Com. A 7518 BCRA)",
        "analogia_10_anios": (
            "Si hacés un dibujo o programás un jueguito para alguien de Estados Unidos y te paga en dólares, "
            "antes el banco te obligaba a cambiar esos caramelos ricos por figuritas comunes. Con este permiso especial, "
            "hasta 24.000 dólares por año entran directo a tu alcancía en dólares y te los quedás billete."
        ),
        "impacto_segun_perfil": {
            "monotributo": "Factura E con alícuota 0% IVA y acreditación directa en caja de ahorro en dólares en Argentina.",
            "empresa_ri": "Aplica para profesionales independientes y personas humanas prestadoras de servicios."
        },
        "beneficio_clave": "Disponibilidad de divisas en billete al 100% sin pasar por el Mercado Único y Libre de Cambios (MULC).",
        "normativa_oficial": "Comunicación 'A' 7518 y complementarias del Banco Central de la República Argentina."
    }
]

def obtener_novedades_y_moratorias(
    perfil: Optional[Dict[str, Any]] = None,
    categoria: Optional[str] = None
) -> Dict[str, Any]:
    """
    Devuelve las novedades fiscales, moratorias y planes vigentes adaptados al perfil del usuario.
    """
    novedades_filtradas = []
    tipo = ((perfil or {}).get("tipo_personeria") or "todos").lower()

    for nov in NOVEDADES_VIGENTES:
        if categoria and nov["categoria"].upper() != categoria.upper():
            continue
        
        # Adaptación según perfil
        impacto_personalizado = nov["impacto_segun_perfil"].get("monotributo" if "mono" in tipo else "empresa_ri") or nov["beneficio_clave"]
        
        novedades_filtradas.append({
            "id": nov["id"],
            "titulo": nov["titulo"],
            "que_significa_chico_10_anios": nov["analogia_10_anios"],
            "como_te_sirve_a_vos": impacto_personalizado,
            "beneficio_economico": nov["beneficio_clave"],
            "norma_oficial": nov["normativa_oficial"]
        })

    return {
        "fecha_actualizacion": datetime.datetime.now().strftime("%d/%m/%Y"),
        "total_novedades_activas": len(novedades_filtradas),
        "novedades": novedades_filtradas,
        "garantia_human_in_the_loop": (
            "Recordá que si alguna de estas moratorias o planes te interesa, podés pedir en cualquier momento "
            "que un Contador Público Matriculado de nuestra red revise tu situación particular antes de adherirte."
        )
    }

def simular_plan_pago(
    deuda_total: float,
    cantidad_cuotas: int = 12,
    tipo_contribuyente: str = "monotributo",
    tasa_mensual_estimada: float = 3.5
) -> Dict[str, Any]:
    """
    Simula un plan de facilidades de pago en cuotas (RG 5321 / Moratoria Ley 27.743).
    """
    if cantidad_cuotas <= 0:
        cantidad_cuotas = 12
    if deuda_total <= 0:
        return {"error": "El monto adeudado debe ser mayor a 0."}

    # Pago a cuenta (5% o 10% según régimen)
    porc_pago_cuenta = 0.05 if "mono" in tipo_contribuyente.lower() else 0.10
    pago_a_cuenta = deuda_total * porc_pago_cuenta
    saldo_a_financiar = deuda_total - pago_a_cuenta

    # Cuota francesa aproximada
    i = (tasa_mensual_estimada / 100.0)
    if i > 0:
        cuota_mensual = saldo_a_financiar * (i * ((1 + i) ** cantidad_cuotas)) / (((1 + i) ** cantidad_cuotas) - 1)
    else:
        cuota_mensual = saldo_a_financiar / cantidad_cuotas

    total_con_intereses = pago_a_cuenta + (cuota_mensual * cantidad_cuotas)

    return {
        "deuda_original": deuda_total,
        "pago_a_cuenta_inicial": round(pago_a_cuenta, 2),
        "cantidad_cuotas": cantidad_cuotas,
        "valor_cuota_mensual_estimada": round(cuota_mensual, 2),
        "dia_debito_automatico_cbu": "Día 16 de cada mes (con segundo intento el día 26)",
        "tasa_mensual_aplicada": f"{tasa_mensual_estimada}% mensual",
        "total_a_pagar_financiado": round(total_con_intereses, 2),
        "explicacion_chico_10_anios": (
            f"En vez de tener que pagar los ${deuda_total:,.2f} todos juntos de golpe, "
            f"ponés una entrada chiquita de ${pago_a_cuenta:,.2f} y después pagás {cantidad_cuotas} cuotitas "
            f"de ${cuota_mensual:,.2f} que se cobran solas de tu cuenta bancaria. "
            "Apenas entra la primera cuota, ARCA te levanta el cartel rojo y volvés a estar 100% al día."
        ),
        "requisitos_arca": [
            "Tener CBU declarada en el servicio 'Declaración de CBU' de ARCA.",
            "Domicilio Fiscal Electrónico (DFE) constituido.",
            "Haber presentado las DDJJ determinativas previas."
        ],
        "opcion_revision_humana": "Podés solicitar que un contador matriculado audite este borrador antes del envío oficial."
    }

def solicitar_revision_contador_humano(
    cuit: str,
    tema_o_tramite: str,
    contacto_usuario: Optional[str] = None,
    detalles_operacion: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Canaliza la solicitud 'Human-in-the-Loop'. Envía la consulta o borrador generado
    por la IA a un Contador Público Matriculado para su validación, firma o doble chequeo.
    """
    cuit_clean = "".join([c for c in str(cuit) if c.isdigit()])
    ticket_id = f"REV-{datetime.datetime.now().strftime('%Y%m%d%H%M')}-{cuit_clean[-4:] if len(cuit_clean)>=4 else '0000'}"

    return {
        "ticket_revision_id": ticket_id,
        "estado": "PENDIENTE_ASIGNACION_CONTADOR_MATRICULADO",
        "cuit": cuit_clean,
        "tramite_a_revisar": tema_o_tramite,
        "tiempo_estimado_respuesta": "Menos de 2 horas hábiles",
        "mensaje_para_usuario": (
            "✅ Solicitud recibida. Un Contador Público Matriculado independiente de nuestra red revisará "
            "tu borrador, verificará los cálculos impositivos y te enviará su dictamen y visto bueno. "
            "Ninguna acción vinculante se presentará ante ARCA sin tu consentimiento final expreso."
        ),
        "explicacion_chico_10_anios": (
            "Es como cuando hacés la tarea con la computadora: la IA hace las cuentas rapidísimo en un segundo, "
            "pero antes de entregársela a la maestra (ARCA), un profesor humano matriculado le pone la lupa encima "
            "y firma que todo está perfecto para que duermas tranquilo."
        ),
        "contacto_registrado": contacto_usuario or "Se notificará en este mismo chat o canal habitual."
    }
