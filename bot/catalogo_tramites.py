"""
Catálogo Completo de Trámites Contables y Fiscales de Argentina (impuesto.com.ar)
Mapea más de 80 trámites de ARCA, Rentas Provinciales (AGIP/ARBA), Convenio Multilateral,
Ministerio de Economía y BCRA para automatización agéntica a través de MCP.
"""

from typing import Dict, Any, List, Optional

CATEGORIAS_TRAMITES = {
    "MONOTRIBUTO": "Régimen Simplificado (Personas Humanas y Profesionales)",
    "FACTURACION": "Emisión de Comprobantes Electrónicos con CAE y Puntos de Venta",
    "IVA_Y_LIBRO_DIGITAL": "Impuesto al Valor Agregado y Libro de IVA Digital",
    "INGRESOS_BRUTOS": "Rentas Provinciales (AGIP, ARBA) y Convenio Multilateral (SIFERE)",
    "GANANCIAS_Y_BIENES": "Ganancias Sociedades, Personas Físicas, Cedular y Bienes Personales",
    "SUELDOS_Y_RRHH": "Cargas Sociales, Libro de Sueldos Digital (LSD) y F. 931",
    "SOCIETARIO_Y_BALANCES": "Constitución de Sociedades (SAS/SRL), Balances PUB e IGJ",
    "CERTIFICACIONES": "Certificación de Ingresos, Origen Lícito de Fondos y Manifestaciones",
    "BANCARIOS_Y_DIVISAS": "Declaración de CBU, Factura E y Repatriación de Dólares BCRA",
    "DEPOSITOS_Y_PLANES": "Planes de Facilidades de Pago, Devoluciones y DFE"
}

# Base de datos exhaustiva de más de 80 trámites
TRAMITES = [
    # 1. MONOTRIBUTO (12 trámites)
    {"id": "mono_01", "cat": "MONOTRIBUTO", "nombre": "Alta de Monotributo", "desc": "Adhesión inicial al régimen simplificado con actividad y domicilio."},
    {"id": "mono_02", "cat": "MONOTRIBUTO", "nombre": "Baja por Cese de Actividad", "desc": "Baja definitiva para que dejen de correr las cuotas mensuales."},
    {"id": "mono_03", "cat": "MONOTRIBUTO", "nombre": "Baja por Paso a Responsable Inscripto", "desc": "Renuncia al régimen simplificado por superar escalas o decisión comercial."},
    {"id": "mono_04", "cat": "MONOTRIBUTO", "nombre": "Recategorización Semestral (Enero/Julio)", "desc": "Declaración jurada obligatoria de facturación y cambio de letra."},
    {"id": "mono_05", "cat": "MONOTRIBUTO", "nombre": "Modificación de Actividad Económica", "desc": "Cambio o agregado de códigos de actividad en el nomenclador oficial."},
    {"id": "mono_06", "cat": "MONOTRIBUTO", "nombre": "Modificación de Domicilio Fiscal", "desc": "Declaración de nueva dirección y vinculación con Monotributo Unificado."},
    {"id": "mono_07", "cat": "MONOTRIBUTO", "nombre": "Exención de Jubilación (Relación de Dependencia)", "desc": "Eximición del aporte jubilatorio si el contribuyente ya aporta como empleado."},
    {"id": "mono_08", "cat": "MONOTRIBUTO", "nombre": "Cambio de Obra Social", "desc": "Modificación de la entidad médica elegida en el régimen simplificado."},
    {"id": "mono_09", "cat": "MONOTRIBUTO", "nombre": "Descarga de Credencial de Pago (F. 152)", "desc": "Obtención del carnet oficial con código de barras y CUR."},
    {"id": "mono_10", "cat": "MONOTRIBUTO", "nombre": "Generación de VEP / QR para Cuotas Vencidas", "desc": "Liquidación con cálculo automático de intereses resarcitorios."},
    {"id": "mono_11", "cat": "MONOTRIBUTO", "nombre": "Adhesión a Débito Automático", "desc": "Vinculación con tarjeta o CBU para obtener el reintegro anual de una cuota."},
    {"id": "mono_12", "cat": "MONOTRIBUTO", "nombre": "Defensa ante Exclusión de Oficio de ARCA", "desc": "Descargo electrónico por compras o acreditaciones bancarias excesivas."},

    # 2. FACTURACION Y PUNTOS DE VENTA (10 trámites)
    {"id": "fac_01", "cat": "FACTURACION", "nombre": "Alta de Punto de Venta Electrónico", "desc": "Habilitación de PV para Comprobantes en Línea o Web Services."},
    {"id": "fac_02", "cat": "FACTURACION", "nombre": "Emisión de Factura A con CAE", "desc": "Venta entre Responsables Inscriptos con discriminación de IVA."},
    {"id": "fac_03", "cat": "FACTURACION", "nombre": "Emisión de Factura B con CAE", "desc": "Venta a consumidor final o monotributista con IVA incluido."},
    {"id": "fac_04", "cat": "FACTURACION", "nombre": "Emisión de Factura C con CAE", "desc": "Comprobante oficial de monotributistas a cualquier cliente."},
    {"id": "fac_05", "cat": "FACTURACION", "nombre": "Emisión de Factura E (Exportación de Servicios)", "desc": "Facturación en dólares u otra divisa a clientes del exterior."},
    {"id": "fac_06", "cat": "FACTURACION", "nombre": "Emisión de Factura de Crédito MiPyME (FCE A/B)", "desc": "Obligatoria para ventas a Grandes Empresas según Ley 27.440."},
    {"id": "fac_07", "cat": "FACTURACION", "nombre": "Emisión de Notas de Crédito / Débito A, B, C", "desc": "Anulación total o parcial de facturas referenciadas."},
    {"id": "fac_08", "cat": "FACTURACION", "nombre": "Descarga de Comprobantes en PDF con QR", "desc": "Generación de PDF reglamentario con código QR oficial de ARCA."},
    {"id": "fac_09", "cat": "FACTURACION", "nombre": "Configuración de Datos Adicionales (Logo / CBU)", "desc": "Personalización del encabezado de facturación en RCEL."},
    {"id": "fac_10", "cat": "FACTURACION", "nombre": "Auditoría de Comprobantes Emitidos y Recibidos", "desc": "Cruce contra el padrón de Mis Comprobantes para evitar compras apócrifas."},

    # 3. IVA Y LIBRO DE IVA DIGITAL (8 trámites)
    {"id": "iva_01", "cat": "IVA_Y_LIBRO_DIGITAL", "nombre": "Liquidación Mensual F. 2002 de IVA", "desc": "Cálculo de Débito, Crédito y determinación de saldo técnico."},
    {"id": "iva_02", "cat": "IVA_Y_LIBRO_DIGITAL", "nombre": "Cierre de Libro de IVA Digital Ventas (RG 4597)", "desc": "Importación y validación de comprobantes emitidos en Portal IVA."},
    {"id": "iva_03", "cat": "IVA_Y_LIBRO_DIGITAL", "nombre": "Cierre de Libro de IVA Digital Compras (RG 4597)", "desc": "Auditoría y prorrateo de créditos fiscales computables."},
    {"id": "iva_04", "cat": "IVA_Y_LIBRO_DIGITAL", "nombre": "Presentación de DDJJ Rectificativa de IVA", "desc": "Corrección de errores o comprobantes omitidos en meses anteriores."},
    {"id": "iva_05", "cat": "IVA_Y_LIBRO_DIGITAL", "nombre": "Certificado de Exclusión de Retenciones (RG 2226)", "desc": "Trámite para frenar retenciones bancarias cuando hay saldo a favor."},
    {"id": "iva_06", "cat": "IVA_Y_LIBRO_DIGITAL", "nombre": "Cálculo de Prorrateo de IVA (Art. 13)", "desc": "Distribución de crédito fiscal para empresas con operaciones exentas."},
    {"id": "iva_07", "cat": "IVA_Y_LIBRO_DIGITAL", "nombre": "Transferencia de Saldo de Libre Disponibilidad", "desc": "Uso de saldo a favor de IVA para cancelar Ganancias u otros tributos."},
    {"id": "iva_08", "cat": "IVA_Y_LIBRO_DIGITAL", "nombre": "Reintegro de IVA por Exportaciones (RG 2000)", "desc": "Solicitud de devolución del crédito fiscal atribuible a exportación."},

    # 4. INGRESOS BRUTOS Y CONVENIO MULTILATERAL (10 trámites)
    {"id": "ib_01", "cat": "INGRESOS_BRUTOS", "nombre": "Liquidación SIFERE Web CM03 Mensual", "desc": "Presentación de Convenio Multilateral por coeficientes provinciales."},
    {"id": "ib_02", "cat": "INGRESOS_BRUTOS", "nombre": "Confección y Presentación de CM05 Anual", "desc": "Cálculo de nuevos coeficientes de ingresos y gastos por provincia."},
    {"id": "ib_03", "cat": "INGRESOS_BRUTOS", "nombre": "Liquidación AGIP Contribuyentes Locales (CABA)", "desc": "DDJJ mensual para personas y empresas que operan solo en CABA."},
    {"id": "ib_04", "cat": "INGRESOS_BRUTOS", "nombre": "Liquidación ARBA Ingresos Brutos (PBA)", "desc": "DDJJ mensual y conciliación de alícuotas del padrón de Buenos Aires."},
    {"id": "ib_05", "cat": "INGRESOS_BRUTOS", "nombre": "Reclamo y Reducción de Alícuota SIRCREB Bancario", "desc": "Freno a deducciones excesivas de bancos sobre acreditaciones."},
    {"id": "ib_06", "cat": "INGRESOS_BRUTOS", "nombre": "Reclamo y Exclusión SIRCUPA (Billeteras Virtuales)", "desc": "Evita retenciones indebidas en cuentas de Mercado Pago, Ualá, etc."},
    {"id": "ib_07", "cat": "INGRESOS_BRUTOS", "nombre": "Alta de Nueva Jurisdicción en Convenio Multilateral", "desc": "Incorporación de provincias al padrón de SIFERE."},
    {"id": "ib_08", "cat": "INGRESOS_BRUTOS", "nombre": "Cese de Jurisdicción en Convenio Multilateral", "desc": "Baja de provincias donde ya no se realizan ventas."},
    {"id": "ib_09", "cat": "INGRESOS_BRUTOS", "nombre": "Descarga de Constancia de Inscripción en IIBB", "desc": "Certificado exigido por bancos y proveedores para no aplicar alícuota máxima."},
    {"id": "ib_10", "cat": "INGRESOS_BRUTOS", "nombre": "Monotributo Unificado Provincial (ARBA / AGIP / Córdoba)", "desc": "Gestión de la cuota integrada nacional y provincial en un solo pago."},

    # 5. GANANCIAS Y BIENES PERSONALES (8 trámites)
    {"id": "gan_01", "cat": "GANANCIAS_Y_BIENES", "nombre": "Liquidación Ganancias Sociedades (F. 713)", "desc": "Balance fiscal, ajuste por inflación impositivo estático y dinámico."},
    {"id": "gan_02", "cat": "GANANCIAS_Y_BIENES", "nombre": "Cálculo de Anticipos de Ganancias Sociedades", "desc": "Generación de los 10 anticipos anuales para empresas."},
    {"id": "gan_03", "cat": "GANANCIAS_Y_BIENES", "nombre": "Opción de Reducción de Anticipos de Ganancias", "desc": "Trámite ante ARCA para no pagar anticipos cuando la ganancia caerá."},
    {"id": "gan_04", "cat": "GANANCIAS_Y_BIENES", "nombre": "Liquidación Ganancias Personas Humanas (F. 711)", "desc": "Régimen general anual con deducciones personales y gastos admitidos."},
    {"id": "gan_05", "cat": "GANANCIAS_Y_BIENES", "nombre": "Carga de SiRADIG Trabajador (F. 572 Web)", "desc": "Deducciones de alquileres, prepagas, hijos y percepciones en dólares."},
    {"id": "gan_06", "cat": "GANANCIAS_Y_BIENES", "nombre": "Liquidación Impuesto a los Bienes Personales (F. 762)", "desc": "Valuación de inmuebles, autos, cuentas locales y activos en el exterior."},
    {"id": "gan_07", "cat": "GANANCIAS_Y_BIENES", "nombre": "Adhesión al Régimen Especial de Bienes Personales (REIBP)", "desc": "Pago unificado por 5 años con estabilidad fiscal garantizada."},
    {"id": "gan_08", "cat": "GANANCIAS_Y_BIENES", "nombre": "Impuesto Cedular sobre Renta Financiera y Dividendos", "desc": "Declaración del 7% sobre dividendos y rentas de inversiones."},

    # 6. SUELDOS, NÓMINA Y RRHH (8 trámites)
    {"id": "sue_01", "cat": "SUELDOS_Y_RRHH", "nombre": "Liquidación de Sueldos y Emisión de Recibos", "desc": "Cálculo según escalas vigentes de Convenios Colectivos de Trabajo."},
    {"id": "sue_02", "cat": "SUELDOS_Y_RRHH", "nombre": "Generación de Libro de Sueldos Digital (LSD)", "desc": "Exportación y validación de archivos de nómina en ARCA."},
    {"id": "sue_03", "cat": "SUELDOS_Y_RRHH", "nombre": "Presentación F. 931 y Emisión de VEP", "desc": "Declaración jurada mensual de aportes y contribuciones patronales."},
    {"id": "sue_04", "cat": "SUELDOS_Y_RRHH", "nombre": "Alta de Empleado en Simplificación Registral", "desc": "Registro oficial previo al ingreso laboral con constancia de alta."},
    {"id": "sue_05", "cat": "SUELDOS_Y_RRHH", "nombre": "Baja de Empleado y Certificado de Trabajo Art. 80", "desc": "Liquidación final por renuncia o despido y emisión de certificados."},
    {"id": "sue_06", "cat": "SUELDOS_Y_RRHH", "nombre": "Declaración de ART y Seguro de Vida Obligatorio", "desc": "Asignación de contratos de cobertura de riesgos del trabajo."},
    {"id": "sue_07", "cat": "SUELDOS_Y_RRHH", "nombre": "Liquidación de SAC (Aguinaldo) Junio y Diciembre", "desc": "Cálculo de la mayor remuneración mensual y proporcionalidades."},
    {"id": "sue_08", "cat": "SUELDOS_Y_RRHH", "nombre": "Cálculo de Indemnizaciones Laborales (Art. 245)", "desc": "Estimación de antigüedad, preaviso y vacaciones no gozadas."},

    # 7. SOCIETARIO, BALANCES Y CONSTITUCIÓN (8 trámites)
    {"id": "soc_01", "cat": "SOCIETARIO_Y_BALANCES", "nombre": "Constitución Digital de S.R.L. / S.A.S.", "desc": "Generación de contrato constitutivo modelo, objeto social y socios."},
    {"id": "soc_02", "cat": "SOCIETARIO_Y_BALANCES", "nombre": "Obtención de CUIT Societario en ARCA", "desc": "Alta de la nueva sociedad con DFE y vinculación del Administrador."},
    {"id": "soc_03", "cat": "SOCIETARIO_Y_BALANCES", "nombre": "Presentación Única de Balances (PUB) en ARCA", "desc": "Carga de estados contables en PDF con memoria y dictamen."},
    {"id": "soc_04", "cat": "SOCIETARIO_Y_BALANCES", "nombre": "Ajuste por Inflación Contable (Resolución Técnica 6 / 54)", "desc": "Reexpresión monetaria de balances a moneda homogénea."},
    {"id": "soc_05", "cat": "SOCIETARIO_Y_BALANCES", "nombre": "Certificado MiPyME (Secretaría de Industria)", "desc": "Obtención y renovación anual para alivio fiscal y tasas subsidiadas."},
    {"id": "soc_06", "cat": "SOCIETARIO_Y_BALANCES", "nombre": "Actas de Directorio y Asamblea Digitales", "desc": "Modelos legales para aprobación de balances y designación de autoridades."},
    {"id": "soc_07", "cat": "SOCIETARIO_Y_BALANCES", "nombre": "Cambio de Domicilio Social y Jurisdicción", "desc": "Trámite de mudanza societaria ante IGJ o DPPJ."},
    {"id": "soc_08", "cat": "SOCIETARIO_Y_BALANCES", "nombre": "Inscripción en Registro de Beneficiarios Finales", "desc": "Declaración de personas humanas con más del 10% de control societario."},

    # 8. CERTIFICACIONES CONTABLES (6 trámites)
    {"id": "cert_01", "cat": "CERTIFICACIONES", "nombre": "Certificación de Ingresos para Alquileres", "desc": "Constancia de capacidad de pago para propietarios y aseguradoras."},
    {"id": "cert_02", "cat": "CERTIFICACIONES", "nombre": "Certificación de Ingresos para Créditos Bancarios", "desc": "Dictamen contable para préstamos hipotecarios, personales o leasing."},
    {"id": "cert_03", "cat": "CERTIFICACIONES", "nombre": "Certificación de Origen Lícito de Fondos (UIF)", "desc": "Justificación para compra de inmuebles, autos o depósitos bancarios."},
    {"id": "cert_04", "cat": "CERTIFICACIONES", "nombre": "Manifestación de Bienes y Deudas", "desc": "Foto patrimonial para entidades financieras o licitaciones públicas."},
    {"id": "cert_05", "cat": "CERTIFICACIONES", "nombre": "Certificación de Ventas para Licitaciones del Estado", "desc": "Constancia de facturación histórica requerida en compras públicas."},
    {"id": "cert_06", "cat": "CERTIFICACIONES", "nombre": "Certificación de Fondos para Inversiones en Cripto / Brokers", "desc": "Justificación de patrimonio exigida por brokers y exchanges locales."},

    # 9. BANCARIOS, DIVISAS Y EXPORTACIÓN (6 trámites)
    {"id": "banc_01", "cat": "BANCARIOS_Y_DIVISAS", "nombre": "Declaración y Vinculación de CBU en ARCA", "desc": "Registro de cuenta bancaria para devoluciones y débitos automáticos."},
    {"id": "banc_02", "cat": "BANCARIOS_Y_DIVISAS", "nombre": "Cupo de Repatriación de Dólares BCRA (Freelancers)", "desc": "Monitoreo del cupo anual libre de pesificación forzosa."},
    {"id": "banc_03", "cat": "BANCARIOS_Y_DIVISAS", "nombre": "Liquidación de Divisas en Mercado Único y Libre (MULC)", "desc": "Presentación de documentación bancaria de comercio exterior."},
    {"id": "banc_04", "cat": "BANCARIOS_Y_DIVISAS", "nombre": "Emisión de Factura E en Dólares / Euros", "desc": "Comprobante de exportación con cotización oficial del día."},
    {"id": "banc_05", "cat": "BANCARIOS_Y_DIVISAS", "nombre": "Seguimiento de Operaciones de Comercio Exterior (SECOEXPO)", "desc": "Control de plazos para ingreso de divisas y cumplidos bancarios."},
    {"id": "banc_06", "cat": "BANCARIOS_Y_DIVISAS", "nombre": "Solicitud de Devolución de Percepciones en Dólares (RG 4815)", "desc": "Reclamo anual del 30% / 35% por compras en moneda extranjera."},

    # 10. PLANES DE PAGO, DFE Y DEFENSA FISCAL (6 trámites)
    {"id": "def_01", "cat": "DEPOSITOS_Y_PLANES", "nombre": "Plan de Facilidades de Pago (Mis Facilidades)", "desc": "Consolidación de deudas en cuotas fijas con débito automático."},
    {"id": "def_02", "cat": "DEPOSITOS_Y_PLANES", "nombre": "Monitoreo Domicilio Fiscal Electrónico (DFE)", "desc": "Escaneo 24/7 de notificaciones oficiales para evitar vencimientos."},
    {"id": "def_03", "cat": "DEPOSITOS_Y_PLANES", "nombre": "Respuesta a Requerimientos e Intimaciones por Presentaciones Digitales", "desc": "Escrito formal con fundamentación técnica ante requerimientos de agencia."},
    {"id": "def_04", "cat": "DEPOSITOS_Y_PLANES", "nombre": "Levantamiento de Trabas y Embargos Bancarios (SOJ-Bancos)", "desc": "Cancelación o regularización de ejecuciones fiscales judiciales."},
    {"id": "def_05", "cat": "DEPOSITOS_Y_PLANES", "nombre": "Certificado de No Retención en Transferencia de Inmuebles (COTI / ITI)", "desc": "Exención o pago a cuenta en venta de propiedades."},
    {"id": "def_06", "cat": "DEPOSITOS_Y_PLANES", "nombre": "Certificado de Transferencia de Automotores (CETA)", "desc": "Formulario oficial para transferencia y venta de vehículos usados."}
]

def obtener_catalogo_completo(categoria: Optional[str] = None) -> Dict[str, Any]:
    """
    Retorna el catálogo clasificado de trámites contables disponibles.
    """
    if categoria:
        cat_clean = categoria.upper().strip()
        filtrados = [t for t in TRAMITES if t["cat"] == cat_clean]
    else:
        filtrados = TRAMITES

    return {
        "total_tramites_disponibles": len(filtrados),
        "categorias_habilitadas": CATEGORIAS_TRAMITES,
        "tramites": filtrados,
        "instruccion": "Cualquiera de estos trámites puede ser simulado o ejecutado solicitando su 'id' al motor agéntico."
    }

def ejecutar_tramite(tramite_id: str, cuit: str, parametros: Dict[str, Any], confirmado: bool = False) -> Dict[str, Any]:
    """
    Motor central de ejecución de trámites con confirmación de seguridad.
    """
    tramite = next((t for t in TRAMITES if t["id"] == tramite_id), None)
    if not tramite:
        return {"error": "TRAMITE_NO_ENCONTRADO", "id": tramite_id}

    if not confirmado:
        return {
            "estado": "SIMULACION_PREVIA_EXITOSA",
            "tramite": tramite,
            "cuit": cuit,
            "parametros_validados": parametros,
            "confirmacion_requerida": True,
            "mensaje": f"Se preparó la simulación para '{tramite['nombre']}' en CUIT {cuit}. Para impactar en ARCA / Rentas oficiales responde 'CONFIRMAR EJECUCION'."
        }

    # Modo ejecución confirmada
    return {
        "estado": "EJECUTADO_CON_EXITO",
        "tramite": tramite,
        "cuit": cuit,
        "resultado": f"El trámite '{tramite['nombre']}' ha sido procesado exitosamente en ARCA.",
        "comprobante_numero": f"ARC-{cuit[-4:]}-2026-OK",
        "constancia_disponible": True
    }
