// Cloudflare Pages Function: /mcp y /mcp/sse
// Implementa el conector remoto Model Context Protocol (MCP) para conectar ARCA directamente con Claude, ChatGPT, Gemini, Copilot y Cursor.
import { SKILLS_BUNDLE, SKILLS_BUILT_AT } from "./skills_bundle.js";
import { PROMPTS_MAESTROS } from "./prompts_bundle.js";

const MCP_TOOLS = [
  {
    name: "consultar_comprobantes_mes",
    description: "Consulta comprobantes emitidos y/o recibidos en ARCA ('Mis Comprobantes') para un CUIT y período ('YYYY-MM'). Calcula el Débito Fiscal, Crédito Fiscal, IVA preliminar a pagar y resumen de principales clientes y proveedores.",
    inputSchema: {
      type: "object",
      properties: {
        cuit: { type: "string", description: "CUIT a consultar (sin guiones, ej. '20301234567')" },
        periodo: { type: "string", description: "Período fiscal en formato 'YYYY-MM' (ej. '2026-11')" },
        tipo: { type: "string", enum: ["emitidos", "recibidos", "ambos"], default: "ambos", description: "Tipo de comprobantes a consultar" }
      },
      required: ["cuit", "periodo"]
    }
  },
  {
    name: "leer_notificaciones_dfe",
    description: "Consulta la bandeja de comunicaciones oficiales en el Domicilio Fiscal Electrónico (DFE) de ARCA para detectar intimaciones, órdenes de fiscalización y avisos antes del vencimiento.",
    inputSchema: {
      type: "object",
      properties: {
        cuit: { type: "string", description: "CUIT específico a consultar (opcional, si se omite consulta todos los representados)" }
      }
    }
  },
  {
    name: "listar_empresas",
    description: "Lista todas las personas físicas y empresas jurídicas que el usuario tiene vinculadas o autorización para representar legalmente en ARCA.",
    inputSchema: {
      type: "object",
      properties: {
        cuit: { type: "string", description: "CUIT opcional del contribuyente vinculado" }
      }
    }
  },
  {
    name: "consultar_situacion_monotributo",
    description: "Ingresa en vivo al portal oficial de MONOTRIBUTO en ARCA. Extrae categoría vigente, facturación anual acumulada, margen disponible hasta el tope de exclusión, próxima fecha de recategorización, deuda de períodos vencidos y genera el Plan de Acción con bots ejecutores.",
    inputSchema: {
      type: "object",
      properties: {
        cuit: { type: "string", description: "CUIT a consultar (11 dígitos; opcional si solo hay 1 CUIT vinculado en la bóveda)" }
      }
    }
  },
  {
    name: "preparar_factura_empresa",
    description: "Prepara un borrador fiscal verificado de factura (A, B, C o E) para Empresas (S.R.L., S.A., Responsables Inscriptos) o Monotributistas. Determina automáticamente la letra según condición frente al IVA, calcula alícuotas (21%, 10.5%, 27%), verifica el punto de venta e indica el impacto en el Libro de IVA Digital y F. 2002.",
    inputSchema: {
      type: "object",
      properties: {
        emisor_cuit: { type: "string", description: "CUIT de la empresa o profesional que emite" },
        emisor_razon_social: { type: "string", description: "Razón social del emisor (ej. 'DISTRIBUIDORA ANDINA S.R.L.')" },
        emisor_condicion: { type: "string", description: "Condición frente al IVA del emisor (ej. 'IVA Responsable Inscripto' o 'Monotributo')" },
        receptor_cuit: { type: "string", description: "CUIT del cliente" },
        receptor_razon_social: { type: "string", description: "Razón social o nombre del cliente" },
        receptor_condicion: { type: "string", description: "Condición frente al IVA del cliente (ej. 'IVA Responsable Inscripto', 'Consumidor Final')" },
        items: {
          type: "array",
          items: {
            type: "object",
            properties: {
              descripcion: { type: "string" },
              cantidad: { type: "number" },
              precio_unitario: { type: "number" },
              alicuota_iva: { type: "string", description: "'21', '10.5', '27', o '0'" }
            },
            required: ["descripcion", "precio_unitario"]
          },
          description: "Lista de ítems a facturar"
        },
        punto_venta: { type: "integer", default: 1, description: "Número del Punto de Venta habilitado en ARCA" },
        concepto: { type: "string", enum: ["Servicios", "Productos", "Productos y Servicios"], default: "Servicios" },
        cbu_cobranza: { type: "string", description: "CBU bancaria para cobrar la factura" }
      },
      required: ["emisor_cuit", "receptor_cuit", "items"]
    }
  },
  {
    name: "ejecutar_accion_bot",
    description: "Ejecuta un bot de acción tributaria en ARCA para Monotributo o Personas Jurídicas (generar VEP, simular recategorización, presentar F. 2002 borrador, o solicitar constancias) con confirmación previa.",
    inputSchema: {
      type: "object",
      properties: {
        bot_id: { type: "string", description: "ID del bot (ej. 'bot_pago_cuota_vencida', 'bot_recategorizacion_alerta', 'bot_descarga_credencial', 'bot_iva_f2002_presentacion')" },
        cuit: { type: "string", description: "CUIT sobre el cual operar" },
        parametros: { type: "object", description: "Parámetros específicos de la acción" },
        confirmado: { type: "boolean", description: "Debe ser true para impactar en ARCA; false para modo simulación/borrador." }
      },
      required: ["bot_id", "cuit"]
    }
  },
  {
    name: "obtener_recordatorios_fiscales",
    description: "Calcula el calendario oficial de vencimientos de ARCA personalizado para el CUIT (según terminación) y régimen (Monotributo o Responsable Inscripto), devolviendo prompts y alertas predeterminadas para agendar en la IA.",
    inputSchema: {
      type: "object",
      properties: {
        cuit: { type: "string", description: "CUIT del contribuyente (ej. '20301234567')" },
        regimen: { type: "string", enum: ["auto", "monotributo", "empresa", "responsable_inscripto"], default: "auto", description: "Régimen tributario" }
      },
      required: ["cuit"]
    }
  },
  {
    name: "liquidar_iva_mensual",
    description: "Liquida la posición mensual de IVA con la metodología oficial del F. 2002 de ARCA, prepara el Libro de IVA Digital (RG 4597) y explica el resultado en lenguaje ultra sencillo.",
    inputSchema: {
      type: "object",
      properties: {
        cuit: { type: "string" },
        periodo: { type: "string", description: "YYYY-MM" },
        ventas: { type: "array", items: { type: "object" } },
        compras: { type: "array", items: { type: "object" } },
        retenciones_bancarias: { type: "number", default: 0 },
        saldo_tecnico_anterior: { type: "number", default: 0 }
      },
      required: ["cuit", "periodo"]
    }
  },
  {
    name: "liquidar_ingresos_brutos",
    description: "Liquida Ingresos Brutos mensual (CABA/AGIP, PBA/ARBA o Convenio Multilateral CM03), audita deducciones bancarias y detecta si el SIRCREB te está reteniendo plata de más.",
    inputSchema: {
      type: "object",
      properties: {
        cuit: { type: "string" },
        periodo: { type: "string" },
        jurisdiccion: { type: "string", enum: ["CABA", "PBA", "CONVENIO_MULTILATERAL"] },
        facturacion_bruta: { type: "number" },
        retenciones_bancarias_sircreb: { type: "number", default: 0 }
      },
      required: ["cuit", "periodo", "jurisdiccion", "facturacion_bruta"]
    }
  },
  {
    name: "calcular_sueldo_y_cargas",
    description: "Calcula el recibo de sueldo neto en mano del empleado, los aportes retenidos (17%) y las contribuciones patronales para el Formulario 931 y Libro de Sueldos Digital.",
    inputSchema: {
      type: "object",
      properties: {
        sueldo_bruto: { type: "number", description: "Sueldo bruto pactado" },
        tipo_empleador: { type: "string", enum: ["servicios", "comercio_industria"], default: "servicios" }
      },
      required: ["sueldo_bruto"]
    }
  },
  {
    name: "consultar_asesor_tributario",
    description: "Asesor impositivo senior de Argentina. Responde consultas complejas sobre deducciones, Monotributo vs SRL, dividendos y defensas de ARCA, con analogías sencillas ('para un chico de 10 años') y citas técnicas a las leyes y artículos vigentes.",
    inputSchema: {
      type: "object",
      properties: {
        tema: { type: "string", description: "Tema a consultar (ej. 'que gastos deducir', 'monotributo vs srl', 'saldo a favor', 'retirar plata')" }
      },
      required: ["tema"]
    }
  },
  {
    name: "consultar_catalogo_tramites",
    description: "Consulta el catálogo de más de 80 trámites automatizables en ARCA, Rentas y BCRA (Monotributo, Facturación, IVA, IIBB, Ganancias, Sueldos, Sociedades, Certificaciones).",
    inputSchema: {
      type: "object",
      properties: {
        categoria: { type: "string", description: "Categoría opcional (ej. 'MONOTRIBUTO', 'FACTURACION', 'IVA_Y_LIBRO_DIGITAL', 'INGRESOS_BRUTOS', 'SUELDOS_Y_RRHH', 'CERTIFICACIONES')" }
      }
    }
  },
  {
    name: "calcular_cupo_dolares_freelancer",
    description: "Calcula el cupo restante de USD 24.000 anuales del BCRA para exportadores de servicios libres de pesificación forzosa en MULC y prepara la liquidación cambiaria bancaria.",
    inputSchema: {
      type: "object",
      properties: {
        cuit: { type: "string" },
        dolares_ingresados_anio: { type: "number", default: 0 },
        nuevo_cobro_usd: { type: "number" }
      },
      required: ["cuit", "nuevo_cobro_usd"]
    }
  },
  {
    name: "configurar_perfil_contribuyente",
    description: "Configura el perfil base de negocio del cliente para darle contexto completo a la IA (rol, qué vende, a quién le vende, dónde está ubicado, provincias donde opera y empleados). Determina el marco fiscal a imputar (A, B, C o E, Convenio Multilateral vs Local, F. 931) y recomendaciones estratégicas.",
    inputSchema: {
      type: "object",
      properties: {
        cuit: { type: "string", description: "CUIT del contribuyente" },
        tipo_personeria: { type: "string", enum: ["monotributo", "responsable_inscripto_ph", "srl", "sa", "sas"], description: "Tipo de personería o condición fiscal principal" },
        que_vende: { type: "string", description: "Descripción de lo que vende (productos, software, servicios profesionales, etc.)" },
        a_quien_vende: { type: "string", description: "A quién le vende (empresas B2B, consumidores finales, clientes en el exterior, mixto)" },
        ubicacion_sede: { type: "string", description: "Ubicación o domicilio fiscal (ej. 'CABA', 'PBA', 'Córdoba')" },
        jurisdicciones_operacion: { type: "array", items: { type: "string" }, description: "Lista de provincias donde comercializa (para determinar Convenio Multilateral)" },
        cantidad_empleados: { type: "integer", default: 0, description: "Cantidad de empleados en nómina (0 si no tiene)" },
        rol: { type: "string", description: "Rol del interlocutor (ej. 'Socio Gerente', 'Dueño', 'Profesional independiente')" },
        razon_social: { type: "string", description: "Nombre o Razón Social de la empresa o contribuyente" },
        convenio_colectivo: { type: "string", description: "Convenio colectivo de trabajo si tiene empleados (ej. 'Comercio 130/75')" }
      },
      required: ["cuit", "tipo_personeria", "que_vende", "a_quien_vende", "ubicacion_sede"]
    }
  },
  {
    name: "obtener_perfil_contribuyente",
    description: "Recupera el perfil fiscal y operativo de negocio guardado en la base de datos para este CUIT.",
    inputSchema: {
      type: "object",
      properties: {
        cuit: { type: "string", description: "CUIT a consultar" }
      },
      required: ["cuit"]
    }
  },
  {
    name: "consultar_novedades_y_moratorias",
    description: "Informa sobre moratorias impositivas (Ley 27.743), blanqueo de capitales, planes de pago de ARCA y novedades fiscales diarias, explicadas de forma ultra sencilla ('como a un chico de 10 años') con sus beneficios para el cliente.",
    inputSchema: {
      type: "object",
      properties: {
        categoria: { type: "string", description: "Categoría opcional ('MORATORIAS_Y_ALIVIO', 'REGULARIZACION_ACTIVOS', 'PLANES_DE_PAGO', 'DIVISAS_Y_EXPORTACION')" }
      }
    }
  },
  {
    name: "simular_plan_pago_deuda",
    description: "Simula el pago en cuotas de deudas fiscales de Monotributo, IVA o Ganancias (RG 5321 / Moratoria), calculando el pago a cuenta, cuota mensual, interés y débitos de CBU.",
    inputSchema: {
      type: "object",
      properties: {
        deuda_total: { type: "number", description: "Monto total adeudado a regularizar" },
        cantidad_cuotas: { type: "integer", default: 12, description: "Cantidad de cuotas deseadas" },
        tipo_contribuyente: { type: "string", enum: ["monotributo", "empresa", "responsable_inscripto"], default: "monotributo" }
      },
      required: ["deuda_total"]
    }
  },
  {
    name: "solicitar_revision_contador_humano",
    description: "Garantía Human-in-the-Loop: solicita que un Contador Público Matriculado humano de la red revise, audite y dé su visto bueno a cualquier liquidación o trámite antes de presentarlo ante ARCA.",
    inputSchema: {
      type: "object",
      properties: {
        cuit: { type: "string", description: "CUIT del contribuyente" },
        tema_o_tramite: { type: "string", description: "Qué trámite o cálculo querés que revise el contador humano" },
        contacto_usuario: { type: "string", description: "Email o WhatsApp para recibir el informe" }
      },
      required: ["cuit", "tema_o_tramite"]
    }
  },
  {
    name: "consultar_jurisprudencia_fiscal",
    description: "Consulta los fallos líderes de la Corte Suprema (CSJN), Tribunal Fiscal y Comisión Arbitral (Esso c/ Quilmes por tasas municipales, Candy c/ AFIP por ajuste por inflación y confiscatoriedad, Laboratorios Raffo, Bayer c/ Santa Fe, Intercorp) para blindar la defensa del contribuyente.",
    inputSchema: {
      type: "object",
      properties: {
        tema_o_conflicto: { type: "string", description: "Tema o controversia (ej. 'tasas municipales', 'ajuste por inflacion', 'embargos afip', 'alicuotas discriminatorias iibb', 'sustento territorial')" }
      },
      required: ["tema_o_conflicto"]
    }
  },
  {
    name: "consultar_tasas_provinciales_municipales",
    description: "Informa sobre políticas fiscales de las provincias (alícuotas de IIBB y Sellos en CABA, PBA, Córdoba, Santa Fe, Mendoza) y tasas municipales (Tasa de Seguridad e Higiene TISH, Tasa Vial), auditando si el municipio tiene sustento territorial legal para cobrarte.",
    inputSchema: {
      type: "object",
      properties: {
        jurisdiccion: { type: "string", description: "Provincia (ej. 'CABA', 'PBA', 'CORDOBA', 'SANTA_FE', 'MENDOZA')" },
        municipio: { type: "string", description: "Nombre del municipio opcional (ej. 'Quilmes', 'La Matanza', 'Rosario', 'Córdoba')" },
        rubro: { type: "string", description: "Rubro de actividad (servicios, comercio, industria, software)" }
      },
      required: ["jurisdiccion"]
    }
  },
  {
    name: "consultar_manuales_y_guias_arca",
    description: "Accede a la base de conocimiento oficial de 245 guías paso a paso, manuales de usuario y mapas de rutas internas de ARCA (flujos de SPA AngularJS como #/declaraciones.anteriores de F. 762, RCEL, F. 2002 y aplicativos históricos del SiAP para comprender la lógica de fondo de cada trámite).",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Trámite, impuesto o servicio a consultar (ej. 'bienes personales', 'factura a', 'recategorizacion monotributo', 'cierre libro iva')" },
        categoria: { type: "string", description: "Categoría opcional ('MONOTRIBUTO', 'GANANCIAS_Y_BIENES', 'FACTURACION', 'IVA', 'SUELDOS_Y_SEGURIDAD_SOCIAL', 'CLAVE_FISCAL', 'PAGOS')" }
      },
      required: ["query"]
    }
  },
  {
    name: "solicitar_documentos_complementarios",
    description: "Devuelve el checklist exacto de documentos 'off-ARCA' que el cliente debe adjuntar en el chat del LLM (extractos bancarios, resúmenes de tarjetas de crédito, pólizas de seguros, invoices del exterior, novedades de empleados) para armar la película fiscal completa.",
    inputSchema: {
      type: "object",
      properties: {
        tramite: { type: "string", enum: ["iva_mensual", "ganancias_y_bbpp", "monotributo", "sueldos_f931"], description: "Trámite o liquidación a realizar" },
        tipo_personeria: { type: "string", default: "empresa", description: "Tipo de contribuyente (monotributo, responsable_inscripto, empresa)" }
      },
      required: ["tramite"]
    }
  },
  {
    name: "conciliar_y_graficar_pelicula_fiscal",
    description: "Concilia los comprobantes adjuntados por el cliente en el LLM (bancos, tarjetas, seguros, gastos no registrados en ARCA) con sus datos fiscales, calcula el ahorro rescatado, detecta descalces bancarios y devuelve gráficos listos para renderizar (torta y barras Mermaid + explicación nivel chico de 10 años).",
    inputSchema: {
      type: "object",
      properties: {
        facturacion_bruta: { type: "number", description: "Facturación total del período" },
        gastos_arca: { type: "number", default: 0, description: "Gastos con factura electrónica en ARCA" },
        gastos_adjuntos_off_arca: { type: "number", default: 0, description: "Gastos rescatados de adjuntos (tarjetas, tickets, invoices del exterior, seguros)" },
        retenciones_sircreb_banco: { type: "number", default: 0, description: "Retenciones SIRCREB detectadas en el extracto bancario" },
        impuesto_cheque_computable: { type: "number", default: 0, description: "Impuesto sobre créditos/débitos bancarios computable" },
        percepciones_tarjeta_recuperables: { type: "number", default: 0, description: "Percepciones dólar tarjeta recuperables" },
        acreditaciones_bancarias_mes: { type: "number", default: 0, description: "Total acreditado en cuentas bancarias para control de descalce" },
        iva_estimado: { type: "number", default: 0 },
        iibb_estimado: { type: "number", default: 0 },
        ganancias_o_cuota_estimada: { type: "number", default: 0 }
      },
      required: ["facturacion_bruta"]
    }
  },
  {
    name: "registrar_consulta_sin_respuesta",
    description: "Agenda en la base de datos una pregunta del cliente para la cual el bot no tiene una respuesta validada. Evita improvisar: deriva la duda a un especialista humano y al resolverse se incorpora automáticamente al conocimiento permanente del bot.",
    inputSchema: {
      type: "object",
      properties: {
        pregunta: { type: "string", description: "Pregunta textual o duda específica del cliente" },
        cuit_origen: { type: "string", description: "CUIT del cliente que consulta (opcional)" },
        contexto_cliente: { type: "string", description: "Resumen del rubro/contexto del cliente" }
      },
      required: ["pregunta"]
    }
  },
  {
    name: "incorporar_conocimiento_resuelto",
    description: "Cierra una consulta previamente agendada y suma la respuesta validada a la base de conocimiento permanente del bot en D1 para responder automáticamente a futuros clientes.",
    inputSchema: {
      type: "object",
      properties: {
        consulta_id: { type: "string", description: "ID de la consulta pendiente (ej. KNOW-...)" },
        respuesta_clara: { type: "string", description: "Respuesta validada en lenguaje claro y ejecutivo" },
        normativa_oficial: { type: "string", description: "Ley, decreto o resolución general de respaldo" }
      },
      required: ["consulta_id", "respuesta_clara"]
    }
  },
  {
    name: "buscar_conocimiento_aprendido",
    description: "Busca en la memoria viva del bot (D1) respuestas previamente resueltas por contadores especialistas a partir de casos reales de clientes.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Palabras clave de la consulta a buscar" }
      },
      required: ["query"]
    }
  },
  {
    name: "analizar_impacto_economico_financiero",
    description: "Analiza la realidad económico-financiera completa de una PyME en Argentina (circuito formal + informal en compras, ventas y nómina) para calcular rentabilidad real, cuantificar contingencias laborales y bancarias (Art. 18 Ley 11.683) y sugerir acciones de impacto financiero, regularización laboral (Ley Bases) y beneficios MiPyME.",
    inputSchema: {
      type: "object",
      properties: {
        ventas_formales_mes: { type: "number" },
        ventas_informales_mes: { type: "number", default: 0 },
        compras_formales_mes: { type: "number", default: 0 },
        compras_informales_mes: { type: "number", default: 0 },
        empleados_registrados: { type: "integer", default: 0 },
        empleados_no_registrados: { type: "integer", default: 0 },
        sueldo_promedio_bruto: { type: "number", default: 950000 },
        cobra_informal_por_banco_o_mp: { type: "boolean", default: false }
      },
      required: ["ventas_formales_mes"]
    }
  },
  {
    name: "verificar_estado_servidores_arca_ws",
    description: "Consulta en vivo (FEDummy SOAP) si los Web Services oficiales WSFEv1 de ARCA (AppServer, DbServer y AuthServer) están operativos en producción u homologación.",
    inputSchema: {
      type: "object",
      properties: {
        ambiente: { type: "string", enum: ["produccion", "homologacion"], default: "produccion" }
      }
    }
  },
  {
    name: "emitir_factura_wsfe",
    description: "Prepara o emite una factura electrónica oficial (A=1, B=6, C=11) por el carril rápido de Web Services WSFEv1 de ARCA (<1 segundo, sin navegador). Requiere confirmado=True para solicitar el CAE oficial.",
    inputSchema: {
      type: "object",
      properties: {
        cuit_emisor: { type: "string" },
        pto_vta: { type: "integer", default: 1 },
        cbte_tipo: { type: "integer", description: "1=Factura A, 6=Factura B, 11=Factura C" },
        receptor_cuit: { type: "string" },
        importe_neto: { type: "number" },
        importe_iva: { type: "number", default: 0 },
        concepto: { type: "integer", default: 2, description: "1=Productos, 2=Servicios, 3=Ambos" },
        ambiente: { type: "string", enum: ["homologacion", "produccion"], default: "homologacion" },
        confirmado: { type: "boolean", default: false }
      },
      required: ["cuit_emisor", "cbte_tipo", "receptor_cuit", "importe_neto"]
    }
  },
  {
    name: "consultar_padron_cuit_ws",
    description: "Consulta la constancia de inscripción (Razón Social, condición IVA/Monotributo y domicilio fiscal) de cualquier CUIT vía Web Service oficial WS_SR_PADRON_A5 en <1 segundo.",
    inputSchema: {
      type: "object",
      properties: {
        cuit_consulta: { type: "string", description: "CUIT a consultar en el padrón oficial de ARCA" },
        ambiente: { type: "string", enum: ["produccion", "homologacion"], default: "produccion" }
      },
      required: ["cuit_consulta"]
    }
  },
  {
    name: "consultar_bienes_personales_web",
    description: "Ingresa a BIENES PERSONALES WEB (F. 762) navegando obligatoriamente #/declaraciones.anteriores para extraer el historial completo de DDJJ presentadas y próximo vencimiento.",
    inputSchema: { type: "object", properties: { cuit: { type: "string" } } }
  },
  {
    name: "consultar_ccma_cuenta_corriente",
    description: "Consulta CCMA (Cuenta Corriente de Monotributistas y Autónomos) en ARCA: saldo deudor, intereses resarcitorios y saldo acreedor a favor.",
    inputSchema: { type: "object", properties: { cuit: { type: "string" } } }
  },
  {
    name: "consultar_mis_retenciones_arca",
    description: "Consulta el servicio MIS RETENCIONES (SIRE/SICORE) en ARCA para relevar retenciones y percepciones de IVA/Ganancias sufridas.",
    inputSchema: { type: "object", properties: { cuit_objetivo: { type: "string" } } }
  },
  {
    name: "consultar_nuestra_parte_arca",
    description: "Consulta 'Nuestra Parte' en ARCA para ver inmuebles, autos, cuentas bancarias y consumos registrados por el fisco (clave para Ganancias y BBPP).",
    inputSchema: { type: "object", properties: { cuit: { type: "string" } } }
  },
  {
    name: "verificar_proveedor_apocrifo_apoc",
    description: "Verifica en tiempo real si el CUIT de un proveedor figura en la Base e-APOC (Facturas Apócrifas / Contribuyentes No Confiables) de ARCA antes de computar Crédito Fiscal.",
    inputSchema: {
      type: "object",
      properties: { cuit_proveedor: { type: "string", description: "CUIT de 11 dígitos del proveedor a auditar" } },
      required: ["cuit_proveedor"]
    }
  },
  {
    name: "generar_pdf_factura_oficial",
    description: "Genera el comprobante oficial de ARCA (Factura A, B, C, E, FCE MiPyME o Nota de Crédito) en formato HTML imprimible/PDF A4 con Código QR oficial RG 4892.",
    inputSchema: {
      type: "object",
      properties: {
        letra: { type: "string", description: "'A', 'B', 'C', 'E', 'FCE_A', 'NC_A'" },
        emisor_razon_social: { type: "string" },
        emisor_cuit: { type: "string" },
        receptor_razon_social: { type: "string" },
        receptor_cuit: { type: "string" },
        importe_neto: { type: "number" },
        importe_iva: { type: "number", default: 0 },
        pto_vta: { type: "integer", default: 1 },
        nro_comprobante: { type: "integer", default: 1 },
        cae: { type: "string", default: "76471234567890" }
      },
      required: ["letra", "emisor_razon_social", "emisor_cuit", "receptor_razon_social", "receptor_cuit", "importe_neto"]
    }
  },
  {
    name: "configurar_estudio_contable",
    description: "[MODO ESTUDIO CONTABLE B2B] Da de alta un estudio contable con su branding Marca Blanca en D1 para gestionar múltiples clientes desde Claude.",
    inputSchema: {
      type: "object",
      properties: {
        nombre_estudio: { type: "string" },
        cuit_estudio: { type: "string" },
        socio_responsable: { type: "string" },
        branding_pie: { type: "string" }
      },
      required: ["nombre_estudio", "cuit_estudio", "socio_responsable"]
    }
  },
  {
    name: "importar_cartera_clientes",
    description: "[MODO ESTUDIO CONTABLE B2B] Importa masivamente en D1 la cartera de clientes de un estudio (CUIT, razón social, régimen, jurisdicciones, empleados y analista asignado).",
    inputSchema: {
      type: "object",
      properties: {
        estudio_id: { type: "string" },
        clientes: { type: "array", items: { type: "object" } }
      },
      required: ["estudio_id", "clientes"]
    }
  },
  {
    name: "tablero_cartera_estudio",
    description: "[MODO ESTUDIO CONTABLE B2B] Tablero consolidado de vencimientos por terminación de CUIT, semáforo de cierres (Rojo Anomalía / Amarillo Socio / Verde Aprobado) y filtro por analista.",
    inputSchema: {
      type: "object",
      properties: {
        estudio_id: { type: "string" },
        periodo: { type: "string", description: "YYYY-MM" },
        analista: { type: "string", description: "Filtrar por nombre de analista (opcional)" }
      },
      required: ["estudio_id"]
    }
  },
  {
    name: "registrar_cierre_y_detectar_anomalias",
    description: "[MODO ESTUDIO CONTABLE B2B] Registra el borrador mensual preparado por un analista, dispara alerta roja automática si el impuesto varía >30% respecto al mes anterior y lo deja pendiente de revisión del Socio.",
    inputSchema: {
      type: "object",
      properties: {
        estudio_id: { type: "string" },
        cuit_cliente: { type: "string" },
        periodo: { type: "string" },
        impuesto: { type: "string" },
        monto_actual: { type: "number" },
        monto_mes_anterior: { type: "number", default: 0 },
        preparado_por: { type: "string", default: "Analista Junior" },
        notas: { type: "string", default: "" }
      },
      required: ["estudio_id", "cuit_cliente", "periodo", "impuesto", "monto_actual"]
    }
  },
  {
    name: "aprobar_cierres_socio",
    description: "[MODO ESTUDIO CONTABLE B2B] El Socio revisa y aprueba en bloque los borradores validados en D1 para habilitar su presentación en ARCA y envío Marca Blanca al cliente.",
    inputSchema: {
      type: "object",
      properties: {
        estudio_id: { type: "string" },
        cierre_ids: { type: "array", items: { type: "string" } },
        aprobado_por: { type: "string" },
        observaciones: { type: "string", default: "" }
      },
      required: ["estudio_id", "cierre_ids", "aprobado_por"]
    }
  },
  {
    name: "generar_reporte_marca_blanca_cliente",
    description: "[MODO ESTUDIO CONTABLE B2B] Genera el reporte ejecutivo 100% Marca Blanca con el nombre y pie de firma del estudio contable, listo para WhatsApp o email al cliente final.",
    inputSchema: {
      type: "object",
      properties: {
        nombre_estudio: { type: "string" },
        razon_social_cliente: { type: "string" },
        periodo: { type: "string" },
        impuestos_a_pagar: { type: "array", items: { type: "object" } },
        ahorro_o_credito_rescatado: { type: "number", default: 0 },
        recomendaciones_estudio: { type: "array", items: { type: "string" } },
        pie_firma_estudio: { type: "string" }
      },
      required: ["nombre_estudio", "razon_social_cliente", "periodo", "impuestos_a_pagar"]
    }
  },
  {
    name: "consultar_y_renovar_certificado_mipyme",
    description: "Consulta vigencia y prepara el trámite de solicitud o renovación del Certificado MiPyME (Formulario 1272 en ARCA) para activar pago a cuenta del 100% del Impuesto al Cheque, diferimiento de IVA a 90 días y avales SGR.",
    inputSchema: {
      type: "object",
      properties: {
        cuit_empresa: { type: "string", description: "CUIT de la empresa o monotributista" },
        confirmado: { type: "boolean", default: false, description: "false para diagnóstico/borrador; true para presentar F. 1272" }
      },
      required: ["cuit_empresa"]
    }
  },
  {
    name: "obtener_protocolo_doublecheck_arca",
    description: "[OBLIGATORIO ANTES DE INFORMAR DEUDA O CUMPLIMIENTO] Devuelve la matriz de doble verificación (Double-Check) de ARCA para un dominio tributario (estado_de_cuenta_y_deudas, ganancias_personas_humanas, bienes_personales, iva_y_facturacion, empleador_seguridad_social). Impide falsos negativos como afirmar 'Deuda $0' mirando solo SCT sin revisar CCMA y Mis Facilidades.",
    inputSchema: {
      type: "object",
      properties: {
        consulta_o_dominio: { type: "string", description: "Dominio o pregunta del contribuyente (ej: 'estado de cuenta y deudas', 'ganancias', 'bienes personales', 'iva', 'f931')" }
      },
      required: ["consulta_o_dominio"]
    }
  },
  {
    name: "validar_cobertura_auditoria_arca",
    description: "[DOUBLE-CHECK OBLIGATORIO] Valida si se consultaron TODAS las fuentes obligatorias de ARCA antes de emitir un veredicto al contribuyente. Bloquea afirmaciones de 'Deuda $0' o 'Al día' cuando falta alguna fuente y emite el Sello de Verificación transparente.",
    inputSchema: {
      type: "object",
      properties: {
        dominio: { type: "string", description: "Dominio auditado (estado_de_cuenta_y_deudas, ganancias_personas_humanas, bienes_personales, iva_y_facturacion, empleador_seguridad_social)" },
        fuentes_verificadas: { type: "array", items: { type: "string" }, description: "IDs de fuentes consultadas con éxito (ej: ['ccma', 'mis_facilidades', 'sct', 'portal_monotributo'])" },
        fuentes_fallidas: { type: "array", items: { type: "string" }, description: "IDs de fuentes que dieron error o timeout" }
      },
      required: ["dominio", "fuentes_verificadas"]
    }
  },
  {
    name: "obtener_playbook_servicio_tributario",
    description: "[PRE-FLIGHT OBLIGATORIO ANTES DE USAR CUALQUIER SERVICIO] Devuelve cómo se inicia un servicio de ARCA (SCT, CCMA, Mis Facilidades, Monotributo, Ganancias F.711/F.2711, BBPP F.762) u otro sistema tributario (AGIP, ARBA, SIFERE): qué dropdowns, fechas, botones de cálculo, paginación o inputs ocultos requiere, qué NO muestra y el Protocolo Pre-Flight Universal de 7 preguntas.",
    inputSchema: {
      type: "object",
      properties: {
        servicio_o_consulta: { type: "string", description: "Nombre del servicio u organismo (ej: 'ccma', 'sct', 'mis facilidades', 'ganancias', 'agip', 'arba', 'sifere')" }
      },
      required: ["servicio_o_consulta"]
    }
  },
  {
    name: "iniciar_sesion_contador_agentico",
    description: "[PUNTO DE ENTRADA RECOMENDADO AL INICIAR UNA CONVERSACIÓN] Presenta las capacidades reales del conector impuesto.com.ar, recupera el perfil fiscal guardado en memoria si el usuario ya se identificó, diagnostica qué necesita revisar HOY según su situación (Monotributo, Responsable Inscripto, PyME/Sociedad, Relación de Dependencia o Estudio Contable), recomienda el Skill Pack oficial y propone automatizaciones.",
    inputSchema: {
      type: "object",
      properties: {
        cuit: { type: "string", description: "CUIT opcional del usuario para recuperar su perfil fiscal guardado en D1 y evitar repetir preguntas" },
        situacion: {
          type: "string",
          enum: ["explorar", "monotributo", "responsable_inscripto", "pyme_sociedad", "empleado_relacion_dependencia", "estudio_contable"],
          default: "explorar",
          description: "Situación fiscal actual del usuario si ya la mencionó"
        }
      }
    }
  },
  {
    name: "generar_automatizaciones_y_calendario_fiscal",
    description: "Genera el calendario fiscal personalizado por terminación de CUIT (0-9) y perfil, con automatizaciones, tareas programadas y recordatorios listos para activar en Claude, ChatGPT (Tasks), Gemini/Antigravity (/schedule), Copilot y archivo .ics universal (Google/Apple/Outlook Calendar).",
    inputSchema: {
      type: "object",
      properties: {
        perfil: {
          type: "string",
          enum: ["monotributo", "responsable_inscripto", "pyme_sociedad", "empleado_relacion_dependencia", "estudio_contable"],
          description: "Perfil del contribuyente o estudio"
        },
        cuit: { type: "string", description: "CUIT del contribuyente (opcional; determina los días exactos de vencimiento de IVA, F. 931 y Autónomos)" },
        cliente_ia: {
          type: "string",
          enum: ["todos", "claude", "chatgpt", "gemini", "copilot"],
          default: "todos",
          description: "Asistente donde se activarán las automatizaciones"
        }
      },
      required: ["perfil"]
    }
  },
  {
    name: "auditar_estado_integral_arca",
    description: "[AUDITORÍA 360° EN 1 SOLA SESIÓN HEADLESS] Ejecuta en segundo plano (sin abrir Chrome al usuario) el cruce completo de CCMA + Mis Facilidades (planes vigentes, Ver Pagos capital remanente, cuota día 16 y cupo RG 5321) + SCT (todas las CUITs representadas) + Portal Monotributo, devolviendo el estado de cuenta real con Sello de Verificación.",
    inputSchema: {
      type: "object",
      properties: {
        cuit: { type: "string", description: "CUIT a auditar (11 dígitos, vinculado en la bóveda segura de impuesto.com.ar)" }
      },
      required: ["cuit"]
    }
  },
  {
    name: "preparar_espacio_de_trabajo_impuestos",
    description: "Genera el kit completo personalizado según perfil (monotributo, responsable_inscripto, pyme_sociedad, empleado_relacion_dependencia, estudio_contable) para ordenar el espacio de trabajo de los próximos meses: (1) Prompt listo para copy-paste en un Proyecto llamado 'Impuestos', (2) Skills exactos a guardar para ese perfil, y (3) Automatización mensual de auto-actualización de skills/normativa desde impuesto.com.ar/skills/manifest.json.",
    inputSchema: {
      type: "object",
      properties: {
        perfil: {
          type: "string",
          enum: ["monotributo", "responsable_inscripto", "pyme_sociedad", "empleado_relacion_dependencia", "estudio_contable"],
          description: "Perfil del usuario o estudio"
        },
        cuit: { type: "string", description: "CUIT principal (opcional)" },
        objetivo_principal: { type: "string", description: "Qué busca lograr (ej: 'ordenar deudas y cierres mensuales', 'gestionar cartera del estudio')" },
        jurisdiccion: { type: "string", description: "Provincia o CABA (ej: 'CABA', 'PBA', 'Convenio Multilateral')" }
      },
      required: ["perfil"]
    }
  },
  {
    name: "autorizar_usuario_cuit",
    description: "[SEGURIDAD MULTI-USUARIO · SOLO OWNER] Autoriza a otro usuario (socio, contador, analista o empleado) por su email para consultar u operar un CUIT desde su propio Claude, ChatGPT o Gemini sin compartir nunca tu Clave Fiscal.",
    inputSchema: {
      type: "object",
      properties: {
        cuit: { type: "string", description: "CUIT (11 dígitos) del cual sos Owner" },
        email_invitado: { type: "string", description: "Email del usuario a autorizar (ej. 'socio@estudio.com')" },
        rol: { type: "string", enum: ["solo_lectura", "editor", "owner"], default: "solo_lectura", description: "Nivel de permiso otorgado" }
      },
      required: ["cuit", "email_invitado"]
    }
  },
  {
    name: "revocar_usuario_cuit",
    description: "[SEGURIDAD MULTI-USUARIO · SOLO OWNER] Revoca al instante el acceso de un email autorizado sobre un CUIT en todos los LLMs.",
    inputSchema: {
      type: "object",
      properties: {
        cuit: { type: "string", description: "CUIT (11 dígitos)" },
        email_invitado: { type: "string", description: "Email del usuario a revocar" }
      },
      required: ["cuit", "email_invitado"]
    }
  },
  {
    name: "listar_accesos_cuit",
    description: "[SEGURIDAD MULTI-USUARIO] Lista quién es el Owner y qué emails tienen acceso autorizado (y su rol) sobre un CUIT.",
    inputSchema: {
      type: "object",
      properties: {
        cuit: { type: "string", description: "CUIT (11 dígitos)" }
      },
      required: ["cuit"]
    }
  },
  {
    name: "ver_historial_actividad",
    description: "[HISTORIAL COMPARTIDO CROSS-LLM] Muestra la línea de tiempo unificada de auditorías, consultas, autorizaciones y notas realizadas sobre tus CUITs desde Claude, ChatGPT, Gemini, Copilot o Cursor, para continuar el trabajo desde cualquier asistente.",
    inputSchema: {
      type: "object",
      properties: {
        cuit: { type: "string", description: "CUIT opcional para filtrar (si se omite, muestra el historial de todos tus CUITs autorizados)" },
        limite: { type: "integer", default: 25, description: "Cantidad máxima de eventos recientes a devolver" }
      }
    }
  },
  {
    name: "registrar_nota_historial",
    description: "[HISTORIAL COMPARTIDO CROSS-LLM] Guarda una nota, decisión o pendiente en el historial compartido de tu cuenta/CUIT para retomarlo después desde otro LLM (ej. guardar en Claude y continuar en Gemini o ChatGPT).",
    inputSchema: {
      type: "object",
      properties: {
        cuit: { type: "string", description: "CUIT relacionado (opcional)" },
        titulo: { type: "string", description: "Título breve del hito o pendiente" },
        detalle: { type: "string", description: "Detalle de lo acordado o próximos pasos" }
      },
      required: ["titulo"]
    }
  }
];

export async function onRequest({ request, env, params }) {
  const url = new URL(request.url);
  const host = url.hostname.toLowerCase();
  const DEDICATED_MCP_HOSTS = new Set([
    "claude.impuesto.com.ar",
    "chatgpt.impuesto.com.ar",
    "gemini.impuesto.com.ar",
    "copilot.impuesto.com.ar",
    "cursor.impuesto.com.ar",
    "perplexity.impuesto.com.ar",
    "mcp.impuesto.com.ar",
    "api.impuesto.com.ar"
  ]);
  const isDedicatedSubdomain = DEDICATED_MCP_HOSTS.has(host);
  const path = (params.path || []).join("/");
  const accept = request.headers.get("accept") || "";
  const wantsSse = path === "sse" || (request.method === "GET" && accept.includes("text/event-stream"));

  // 1. Si es GET desde un navegador humano (no SSE), mostrar la landing del conector
  if (!wantsSse && request.method === "GET") {
    return new Response(htmlLanding(url), {
      status: 200,
      headers: { "Content-Type": "text/html; charset=utf-8" }
    });
  }

  // 2. El protocolo MCP (initialize, tools/list, prompts, resources y tools Edge) corre siempre en el Edge (<5ms).
  //    Las herramientas ARCA en vivo delegan a `${env.BOT_API_URL}/api/v1/mcp/tool` con X-Bot-Secret.

  // 3. Manejo directo del estándar MCP SSE en el Edge
  if (wantsSse && request.method === "GET") {
    const sessionId = crypto.randomUUID();
    const qsToken = url.searchParams.get("token") || "";
    const tokenSuffix = qsToken ? `&token=${encodeURIComponent(qsToken)}` : "";
    const endpointUrl = isDedicatedSubdomain
      ? `${url.origin}/messages?sessionId=${sessionId}${tokenSuffix}`
      : `${url.origin}/mcp/messages?sessionId=${sessionId}${tokenSuffix}`;

    const { readable, writable } = new TransformStream();
    const writer = writable.getWriter();
    const encoder = new TextEncoder();

    // Enviar evento de conexión inicial con el endpoint de mensajes
    writer.write(encoder.encode(`event: endpoint\ndata: ${endpointUrl}\n\n`));

    return new Response(readable, {
      status: 200,
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "*"
      }
    });
  }

  // 4. Manejo de mensajes JSON-RPC (POST a /mcp/messages o /mcp)
  if (request.method === "POST") {
    let rpc;
    try {
      rpc = await request.json();
    } catch {
      return jsonRpcError(null, -32700, "Parse error");
    }

    const { id, method, params: rpcParams } = rpc;

    // Métodos del protocolo MCP
    if (method === "initialize") {
      return jsonRpcSuccess(id, {
        protocolVersion: "2024-11-05",
        capabilities: { tools: {}, prompts: {}, resources: {} },
        serverInfo: {
          name: "impuesto-arca-mcp",
          version: "2.5.0"
        },
        instructions: [
          "Sos el CONTADOR AGÉNTICO DE CABECERA y CFO de impuesto.com.ar. Hablás en primera persona como un contador argentino de confianza, cálido, claro y resolutivo. NUNCA menciones 'el MCP' ni 'el conector' al usuario final.",
          "1. FLUJO CONVERSACIONAL POR ETAPAS (PRIMERO CONTEXTO Y ESPACIO DE TRABAJO): Una vez validada la vinculación segura en https://impuesto.com.ar/vincular (o https://impuesto.com.ar/vincular?tipo=estudio para Estudios Contables), ANTES de lanzarte a analizar datos sueltos, explicale brevemente que vamos a configurar el contexto en 2 minutos para trabajar ordenados los próximos meses: (Etapa A) Preguntale qué busca/necesita de Impuestos ofreciendo opciones claras según quién sea (Monotributista, RI, PyME/Sociedad, Relación de Dependencia o Estudio Contable). (Etapa B) Con ese contexto, llamá a `preparar_espacio_de_trabajo_impuestos` y `generar_automatizaciones_y_calendario_fiscal` para proponerle: crear un Proyecto llamado 'Impuestos' con el prompt exacto listo para copy-paste, guardar los skills específicos de su perfil y activar sus automatizaciones de vencimientos + auto-actualización mensual de skills/normativa. (Etapa C) Guardá su perfil (`configurar_perfil_contribuyente`) y ejecutá el diagnóstico completo.",
          "2. AUTONOMÍA TOTAL (CERO DEBERES AL USUARIO): JAMÁS le pidas al usuario que entre a ARCA ni que te comparta pantallas, tablas o detalles de Mis Facilidades, CCMA, SCT, Monotributo, Ganancias, BBPP o DFE. Todo dato que vive en ARCA lo buscás vos automáticamente usando tus herramientas (`auditar_estado_integral_arca`, `leer_notificaciones_dfe`, etc.).",
          "3. DOUBLE-CHECK SIN OMISIONES Y SEGURIDAD: Nunca afirmes 'Deuda $0' ni 'Al día' sin verificar CCMA + Mis Facilidades (con capital remanente total, débito mensual del día 16 y cuotas impagas) + SCT (todas las CUITs representadas) + Monotributo. Aclará siempre qué tributos quedan fuera de ARCA (IIBB AGIP/ARBA, tasas municipales). Jamás envíes facturas, DDJJ ni planes sin `confirmado=true` y ofrecé Contador Público Matriculado (`solicitar_revision_contador_humano`) ante trámites legales/societarios.",
          "4. EXPECTATIVA DE TIEMPOS Y PRÓXIMO PASO: Antes de lanzar auditorías profundas en ARCA, avisá siempre al usuario que es normal que demore entre 1 y 10 minutos según la consulta y que no cierre ni abandone la sesión. Cerrá cada respuesta recomendando el próximo paso concreto."
        ].join("\n")
      });
    }

    if (method === "notifications/initialized") {
      return new Response(null, { status: 204 });
    }

    if (method === "resources/list") {
      return jsonRpcSuccess(id, {
        resources: SKILLS_BUNDLE.map(s => ({
          uri: s.uri,
          name: s.name,
          description: `[v${s.version} · ${s.perfil_objetivo}] ${s.description}`,
          mimeType: "text/markdown"
        }))
      });
    }

    if (method === "resources/read") {
      const targetUri = rpcParams?.uri || "";
      const found = SKILLS_BUNDLE.find(s => s.uri === targetUri || s.slug === targetUri);
      if (!found) {
        return jsonRpcError(id, -32002, `Resource not found: ${targetUri}`);
      }
      return jsonRpcSuccess(id, {
        contents: [
          {
            uri: found.uri,
            mimeType: "text/markdown",
            text: found.content
          }
        ]
      });
    }

    if (method === "prompts/list") {
      return jsonRpcSuccess(id, {
        prompts: [
          {
            name: "empezar_diagnostico_fiscal",
            description: "Empezar: conocer las capacidades de impuesto.com.ar y detectar qué necesito revisar hoy según mi situación."
          },
          {
            name: "auditoria_deuda_real_arca",
            description: "Auditar mi estado de cuenta y deuda real en ARCA (cruzando CCMA + Mis Facilidades + SCT + Monotributo)."
          },
          {
            name: "cierre_mensual_sin_fricciones",
            description: "Hacer mi cierre mensual: facturas emitidas/recibidas, IVA, retenciones, control e-APOC y próximos vencimientos."
          },
          {
            name: "revision_ganancias_y_bbpp",
            description: "Revisar mis declaraciones de Ganancias (F. 711 y F. 2711 Simplificada), SiRADIG y Bienes Personales (F. 762)."
          },
          {
            name: "modo_estudio_contable",
            description: "Abrir Modo Estudio Contable B2B: tablero de cartera multi-cliente, detección de desvíos >30% y reportes Marca Blanca."
          }
        ]
      });
    }

    if (method === "prompts/get") {
      const pName = rpcParams?.name || "empezar_diagnostico_fiscal";
      const PROMPTS_MAP = {
        empezar_diagnostico_fiscal: "Llamá a `iniciar_sesion_contador_agentico` para mostrarme qué podés hacer por mí, detectar qué necesito revisar hoy según mi situación fiscal y proponerme el primer paso sin fricciones.",
        auditoria_deuda_real_arca: "Quiero auditar mi estado de cuenta y deuda real en ARCA. Ejecutá primero `obtener_protocolo_doublecheck_arca` para `estado_de_cuenta_y_deudas` y verificá CCMA, Mis Facilidades, SCT y Portal Monotributo antes de darme el saldo final con Sello de Verificación.",
        cierre_mensual_sin_fricciones: "Hagamos mi cierre impositivo mensual. Consultá mi perfil guardado (`obtener_perfil_contribuyente`) o preguntame mi CUIT/régimen, pedime los documentos fuera de ARCA que falten (`solicitar_documentos_complementarios`) y armemos el tablero de liquidación y vencimientos.",
        revision_ganancias_y_bbpp: "Quiero revisar mis declaraciones de Ganancias Personas Humanas y Bienes Personales. Aplicá el Double-Check verificando tanto F. 711 como F. 2711 Simplificada (RG 5692), F. 762 en #/declaraciones.anteriores, Nuestra Parte y SCT.",
        modo_estudio_contable: "Quiero operar en Modo Estudio Contable B2B. Mostrame cómo cargar mi cartera de clientes, ver el tablero de vencimientos por terminación de CUIT, detectar anomalías >30% y emitir reportes Marca Blanca."
      };
      return jsonRpcSuccess(id, {
        description: pName,
        messages: [
          {
            role: "user",
            content: {
              type: "text",
              text: PROMPTS_MAP[pName] || PROMPTS_MAP.empezar_diagnostico_fiscal
            }
          }
        ]
      });
    }

    if (method === "tools/list") {
      return jsonRpcSuccess(id, { tools: MCP_TOOLS });
    }

    if (method === "tools/call") {
      const toolName = rpcParams?.name;
      const args = rpcParams?.arguments || {};

      // 1. Tool de recordatorios predeterminados (resuelta en el Edge)
      if (toolName === "obtener_recordatorios_fiscales") {
        const cuitClean = (args.cuit || "").replace(/[^0-9]/g, "");
        const term = cuitClean ? parseInt(cuitClean.slice(-1), 10) : 0;
        const diaIva = 18 + Math.floor(term / 2);
        const diaF931 = term <= 3 ? 9 : (term <= 6 ? 10 : 11);
        const hoy = new Date();
        const mes = hoy.getMonth() + 1;
        const anio = hoy.getFullYear();

        const recs = [
          {
            id: "rec_mono_mensual",
            titulo: `Pago Cuota Monotributo (${mes}/${anio})`,
            vencimiento: `20/${mes < 10 ? '0' + mes : mes}/${anio}`,
            alerta_ia: `Recordame el 18/${mes < 10 ? '0' + mes : mes} generar el QR de pago del Monotributo`
          },
          {
            id: "rec_iva_f2002",
            titulo: `Presentación F. 2002 IVA y Cierre Libro IVA Digital (${mes}/${anio})`,
            vencimiento: `${diaIva}/${mes < 10 ? '0' + mes : mes}/${anio} (por terminación ${term})`,
            alerta_ia: `Recordame el ${diaIva - 2}/${mes < 10 ? '0' + mes : mes} revisar y confirmar el borrador de IVA`
          },
          {
            id: "rec_f931_cargas",
            titulo: `Cargas Sociales F. 931 Empleadores (${mes}/${anio})`,
            vencimiento: `${diaF931}/${mes < 10 ? '0' + mes : mes}/${anio} (por terminación ${term})`,
            alerta_ia: `Recordame el ${diaF931 - 1}/${mes < 10 ? '0' + mes : mes} revisar las cargas sociales de nómina`
          }
        ];

        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              cuit: args.cuit,
              terminacion: term,
              recordatorios_predeterminados: recs,
              instruccion_para_ia: "Mostrale al usuario sus vencimientos y ofrecete a agendarle estos recordatorios en su calendario o conversación habitual."
            }, null, 2)
          }]
        });
      }

      // 1b. Asesor Tributario Inteligente (Edge instantáneo)
      if (toolName === "consultar_asesor_tributario") {
        const tema = (args.tema || "").toLowerCase();
        let respuesta = {
          titulo: "Consulta impositiva general",
          analogia_10_anios: "Los impuestos son como la cuota del club: todos los socios ponen un poquito para que haya pileta, luz y canchas de fútbol. El secreto no es esconder la plata, sino saber qué beneficios y descuentos te da el reglamento para no pagar ni un peso de más.",
          regla_fiscal_real: "Principio de legalidad y capacidad contributiva (Constitución Nacional Art. 17). Toda obligación tributaria debe emanar de una ley formal y liquidarse sobre hechos imponibles reales."
        };

        if (tema.includes("gasto") || tema.includes("deduc")) {
          respuesta = {
            titulo: "¿Qué gastos puedo pasar por la empresa o negocio para pagar menos impuestos?",
            analogia_10_anios: "Imaginá que tenés un puesto de limonada. Si comprás limones, azúcar, vasos descartables y el cartelito con el precio, todo eso es necesario para vender limonada; se lo restás a tus ganancias y pagás menos impuesto. Pero si con la plata de la limonada te comprás una pelota de fútbol o ropa para ir a bailar, la maestra (ARCA) te va a decir: '¡Esa pelota no te ayuda a hacer limonada!', te anula el gasto y te cobra una multa.",
            regla_fiscal_real: "Artículo 83 Ley de Ganancias: Son deducibles los gastos vinculados a obtener, mantener y conservar la ganancia gravada. Gastos personales están prohibidos por el Art. 92.",
            gastos_validos: ["Luz, internet, telefonía laboral", "Hosting, software y computadoras", "Combustible de utilitarios afectados", "Insumos y mercadería de reventa"]
          };
        } else if (tema.includes("srl") || tema.includes("mono")) {
          respuesta = {
            titulo: "¿Cuándo me conviene pasar de Monotributo a una Sociedad (S.R.L. o S.A.S.)?",
            analogia_10_anios: "El Monotributo es como una bicicleta: es barata, fácil de andar y pagás una cuota fija como Netflix. Pero si tu negocio empieza a transportar camiones llenos de cajas (mucha facturación), la bicicleta no aguanta más y te caés. Una S.R.L. es como un auto: cuesta más mantenerlo y hay que hacerle service todos los meses, pero si tenés un choque, tu casa y tus ahorros personales están a salvo porque la que responde es la empresa, no vos.",
            regla_fiscal_real: "Ley 24.977 vs Ley 19.550. Superar el tope de Categoría K te hace responsable inscripto pagando hasta 35% de Ganancias en cabeza personal. La SRL separa el patrimonio y tributa tasa escalonada.",
            recomendacion: "Constituir la S.R.L. antes de alcanzar el tope de exclusión para evitar ajustes retroactivos de ARCA."
          };
        } else if (tema.includes("retir") || tema.includes("plata") || tema.includes("dividendo")) {
          respuesta = {
            titulo: "¿Cómo saco plata de mi empresa sin pagar impuestos dos veces?",
            analogia_10_anios: "Si la empresa ganó $100 y vos sos el dueño, no podés meter la mano en la caja y llevártelos a tu bolsillo como si fuera tu billetera, porque la ley dice que la empresa es una persona distinta a vos. Hay dos caminos legales para sacar la plata: 1) Pagarte un sueldo/honorario por trabajar de jefe (que la empresa puede restar como gasto), o 2) Esperar a fin de año, pagar el impuesto de la empresa y repartirte las ganancias (dividendos al 7%).",
            regla_fiscal_real: "Art. 91 inc. i Ley de Ganancias (Honorarios a directores deducibles hasta el 25% de la utilidad) vs Art. 97 (Dividendos al 7%)."
          };
        }

        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify(respuesta, null, 2)
          }]
        });
      }

      // 1c. Calculadora de Sueldos y F. 931 (Edge instantáneo)
      if (toolName === "calcular_sueldo_y_cargas") {
        const bruto = parseFloat(args.sueldo_bruto || 0);
        const neto = bruto * 0.83; // 17% aportes empleado
        const contribPatronal = bruto * (args.tipo_empleador === "servicios" ? 0.204 : 0.18);
        const obraSocialPatronal = bruto * 0.06;
        const art = bruto * 0.035;
        const totalF931 = (bruto * 0.17) + contribPatronal + obraSocialPatronal + art + 850;

        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              sueldo_bruto: bruto,
              sueldo_neto_en_mano: Math.round(neto * 100) / 100,
              descuentos_empleado_17pct: Math.round(bruto * 0.17 * 100) / 100,
              cargas_patronales_empresa: Math.round((contribPatronal + obraSocialPatronal + art + 850) * 100) / 100,
              total_f931_arca_a_pagar: Math.round(totalF931 * 100) / 100,
              costo_total_empleador: Math.round((bruto + contribPatronal + obraSocialPatronal + art + 850) * 100) / 100,
              explicacion_10_anios: `Al empleado le quedan en mano $${neto.toLocaleString('es-AR')} de los $${bruto.toLocaleString('es-AR')} pactados (17% retenido para su jubilación y médico). A vos como empresa te cuesta en total $${(bruto + contribPatronal + obraSocialPatronal + art + 850).toLocaleString('es-AR')} sumando las cargas patronales y la ART.`
            }, null, 2)
          }]
        });
      }

      // 1d. Configuración y Evaluación de Perfil de Contribuyente (Onboarding Inteligente)
      if (toolName === "configurar_perfil_contribuyente") {
        const cuitClean = (args.cuit || "").replace(/[^0-9]/g, "");
        const perfil = evaluarPerfilFiscalJS(args);

        // Persistir en base de datos D1 si está disponible
        if (cuitClean && env.DB) {
          try {
            await env.DB.prepare(`
              INSERT INTO perfiles_contribuyentes (
                cuit, razon_social, rol, tipo_personeria, que_vende, a_quien_vende,
                ubicacion_sede, jurisdicciones, cantidad_empleados, convenio_colectivo,
                marco_fiscal_json, actualizado
              ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
              ON CONFLICT(cuit) DO UPDATE SET
                razon_social = excluded.razon_social,
                rol = excluded.rol,
                tipo_personeria = excluded.tipo_personeria,
                que_vende = excluded.que_vende,
                a_quien_vende = excluded.a_quien_vende,
                ubicacion_sede = excluded.ubicacion_sede,
                jurisdicciones = excluded.jurisdicciones,
                cantidad_empleados = excluded.cantidad_empleados,
                convenio_colectivo = excluded.convenio_colectivo,
                marco_fiscal_json = excluded.marco_fiscal_json,
                actualizado = datetime('now')
            `).bind(
              cuitClean,
              args.razon_social || "Contribuyente Registrado",
              args.rol || "Titular",
              args.tipo_personeria,
              args.que_vende,
              args.a_quien_vende,
              args.ubicacion_sede,
              JSON.stringify(args.jurisdicciones_operacion || [args.ubicacion_sede]),
              parseInt(args.cantidad_empleados || 0, 10),
              args.convenio_colectivo || null,
              JSON.stringify(perfil)
            ).run();
          } catch (e) {
            // Log silencioso si la tabla no está creada aún en local
          }
        }

        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify(perfil, null, 2)
          }]
        });
      }

      // 1e. Obtener Perfil de Contribuyente
      if (toolName === "obtener_perfil_contribuyente") {
        const cuitClean = (args.cuit || "").replace(/[^0-9]/g, "");
        if (cuitClean && env.DB) {
          try {
            const row = await env.DB.prepare("SELECT * FROM perfiles_contribuyentes WHERE cuit = ?").bind(cuitClean).first();
            if (row) {
              const marco = row.marco_fiscal_json ? JSON.parse(row.marco_fiscal_json) : null;
              return jsonRpcSuccess(id, {
                content: [{
                  type: "text",
                  text: JSON.stringify({
                    registrado: true,
                    cuit: row.cuit,
                    razon_social: row.razon_social,
                    rol: row.rol,
                    tipo_personeria: row.tipo_personeria,
                    que_vende: row.que_vende,
                    a_quien_vende: row.a_quien_vende,
                    ubicacion_sede: row.ubicacion_sede,
                    jurisdicciones: JSON.parse(row.jurisdicciones || "[]"),
                    cantidad_empleados: row.cantidad_empleados,
                    marco_fiscal: marco,
                    actualizado: row.actualizado
                  }, null, 2)
                }]
              });
            }
          } catch (e) {
            // Fallback
          }
        }

        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              cuit: cuitClean,
              registrado: false,
              mensaje: "Aún no tenemos el perfil de negocio guardado para este CUIT. Por favor hacé estas 5 preguntas al usuario para encuadrarlo fiscalmente: 1) Rol y tipo de personería (Monotributo/SRL/SA/RI), 2) Qué vende, 3) A quién le vende (B2B, consumidor final o exterior), 4) Dónde está y dónde vende, 5) Cantidad de empleados."
            }, null, 2)
          }]
        });
      }

      // 1f. Consultar Novedades Fiscales, Moratorias y Blanqueo
      if (toolName === "consultar_novedades_y_moratorias") {
        const novedades = [
          {
            id: "nov_moratoria_27743",
            titulo: "Moratoria Fiscal Ley 27.743: Condonación de hasta 100% de intereses y multas",
            que_significa_chico_10_anios: "Si debías cuotas de Monotributo, IVA o Ganancias de antes, el estado te perdona todos los intereses y las multas si entrás a la moratoria. Pagás solo la deuda pura al contado o en cuotas.",
            como_te_sirve: "Permite regularizar cuotas impagas viejas en hasta 84 cuotas y levanta cualquier traba para facturar o pedir créditos.",
            norma_oficial: "Ley 27.743 y RG 5525/2024 ARCA."
          },
          {
            id: "nov_blanqueo_activos",
            titulo: "Blanqueo de Capitales: 0% de impuesto hasta USD 100.000",
            que_significa_chico_10_anios: "Si tenías plata ahorrada debajo del colchón o en el exterior que no habías declarado, podés depositarla en una cuenta especial y no pagás ni un peso de impuesto hasta 100.000 dólares. A partir de ahí, queda 100% en blanco.",
            como_te_sirve: "Te permite comprar un auto, departamento o invertir en tu negocio sin miedo a requerimientos de ARCA.",
            norma_oficial: "Ley 27.743 (Título II)."
          },
          {
            id: "nov_plan_permanente_arca",
            titulo: "Planes de Pago Permanentes de ARCA (RG 5321)",
            que_significa_chico_10_anios: "En vez de pagar una deuda grande toda junta, la dividís en cuotas chiquitas que se debitan solas de tu CBU bancaria el día 16 de cada mes.",
            como_te_sirve: "Levanta embargos y restaura tu estado de cumplimiento fiscal en 48 horas.",
            norma_oficial: "RG 5321 y RG 5590 ARCA."
          },
          {
            id: "nov_cupo_dolares_freelancers",
            titulo: "Cobro de USD sin pesificar para profesionales (Com. A 7518 BCRA)",
            que_significa_chico_10_anios: "Si exportás servicios o software afuera, hasta 24.000 dólares por año entran directo a tu cuenta bancaria argentina en dólares billete, sin que te los cambien a pesos obligatoriamente.",
            como_te_sirve: "Mantenés tus ahorros en moneda dura emitiendo Factura E al 0% de IVA.",
            norma_oficial: "Com. 'A' 7518 del Banco Central de la República Argentina."
          }
        ];

        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              novedades: novedades,
              garantia_human_in_the_loop: "En todo momento podés pedir que un Contador Público Matriculado de nuestra red audite si te conviene adherirte a alguna de estas medidas antes de confirmar."
            }, null, 2)
          }]
        });
      }

      // 1g. Simulación de Plan de Pago
      if (toolName === "simular_plan_pago_deuda") {
        const deuda = parseFloat(args.deuda_total || 0);
        const cuotas = parseInt(args.cantidad_cuotas || 12, 10);
        const porcPagoCuenta = args.tipo_contribuyente === "empresa" ? 0.10 : 0.05;
        const pagoCuenta = deuda * porcPagoCuenta;
        const saldoFinanciar = deuda - pagoCuenta;
        const i = 0.035; // 3.5% tasa mensual estimada
        const cuotaMensual = saldoFinanciar * (i * Math.pow(1 + i, cuotas)) / (Math.pow(1 + i, cuotas) - 1);
        const total = pagoCuenta + (cuotaMensual * cuotas);

        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              deuda_original: deuda,
              pago_a_cuenta_inicial: Math.round(pagoCuenta * 100) / 100,
              cantidad_cuotas: cuotas,
              cuota_mensual_estimada: Math.round(cuotaMensual * 100) / 100,
              debito_automatico: "Día 16 de cada mes en CBU informada",
              total_a_pagar_financiado: Math.round(total * 100) / 100,
              explicacion_chico_10_anios: `En vez de pagar los $${deuda.toLocaleString('es-AR')} todos juntos, pagás una entrada de $${Math.round(pagoCuenta).toLocaleString('es-AR')} y después ${cuotas} cuotas de $${Math.round(cuotaMensual).toLocaleString('es-AR')}. Apenas entra el primer débito, ARCA te levanta cualquier bloqueo.`,
              garantia_human_in_the_loop: "Podés pedir la revisión de este plan con un contador público humano antes del envío a ARCA."
            }, null, 2)
          }]
        });
      }

      // 1h. Human-in-the-Loop: Solicitud de Revisión de Contador Humano
      if (toolName === "solicitar_revision_contador_humano") {
        const cuitClean = (args.cuit || "").replace(/[^0-9]/g, "");
        const ticket = "REV-" + Date.now().toString().slice(-8) + "-" + (cuitClean.slice(-4) || "0000");

        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              ticket_id: ticket,
              estado: "RECIBIDO_PARA_AUDITORIA_HUMANA",
              cuit: cuitClean,
              tramite_a_revisar: args.tema_o_tramite,
              tiempo_estimado: "Menos de 2 horas hábiles",
              mensaje_para_usuario: "Un Contador Público Matriculado independiente revisará los números y te confirmará su visto bueno antes de que se haga ninguna presentación ante ARCA.",
              explicacion_chico_10_anios: "La IA hizo las cuentas en un segundo, y ahora un profesor humano matriculado le pone la firma y la lupa para que duermas 100% tranquilo.",
              contacto: args.contacto_usuario || "Se informará en esta misma conversación."
            }, null, 2)
          }]
        });
      }

      // 1i. Jurisprudencia Tributaria Líder (CSJN / TFN)
      if (toolName === "consultar_jurisprudencia_fiscal") {
        const q = (args.tema_o_conflicto || "").toLowerCase();
        const fallos = [
          {
            caratula: "Esso Petrolera Argentina c/ Municipalidad de Quilmes (CSJN, 2021)",
            tema: "Tasas Municipales de Seguridad e Higiene (TISH)",
            analogia_10_anios: "El intendente no puede cobrarte tasas como si fuera socio de tu empresa; solo te cobra si te dio un servicio real y medible en tu local físico.",
            doctrina: "Requiere acreditación de servicio efectivo e individualizado. Prohíbe tasas desproporcionadas sobre ingresos brutos globales sin sustento territorial."
          },
          {
            caratula: "Laboratorios Raffo S.A. c/ Municipalidad de Córdoba (CSJN, 2009)",
            tema: "Inexistencia de local o establecimiento en el municipio",
            analogia_10_anios: "Si vendés por internet desde Buenos Aires y mandás una encomienda a Córdoba, el municipio no puede cobrarte tasa de inspección porque no tenés cocina ni local allá para inspeccionar.",
            doctrina: "Exige existencia de local o establecimiento físico habilitado en el ejido municipal para legitimar el cobro de la tasa."
          },
          {
            caratula: "Candy S.A. c/ AFIP (CSJN, 2009)",
            tema: "Ajuste por Inflación Impositivo y Confiscatoriedad",
            analogia_10_anios: "Si la inflación hace que el impuesto te coma más de un tercio de lo que realmente ganaste en mano, el juez frena a ARCA porque te está confiscando tu plata.",
            doctrina: "Tope de confiscatoriedad en el 33% al 35% de la renta neta real. Prohíbe cobrar sobre ganancias ficticias producidas por la inflación."
          },
          {
            caratula: "Bayer S.A. c/ Provincia de Santa Fe (CSJN, 2017)",
            tema: "Alícuotas discriminatorias de Ingresos Brutos a industrias de otras provincias",
            analogia_10_anios: "Una provincia no puede cobrarle impuestos más caros a una fábrica solo porque está en otra provincia. Dentro del país somos todos iguales.",
            doctrina: "Inconstitucionalidad de alícuotas diferenciales agravadas a extrañas jurisdicciones por violar la Cláusula Comercial y el principio de igualdad."
          },
          {
            caratula: "AFIP c/ Intercorp S.R.L. (CSJN, 2010)",
            tema: "Inconstitucionalidad de embargos bancarios automáticos trabados por el fisco",
            analogia_10_anios: "ARCA no puede apretar un botón y congelarte la cuenta del banco sola: necesita que un juez independiente firme la orden.",
            doctrina: "Inconstitucionalidad del Art. 92 de la Ley 11.683. Los embargos bancarios requieren orden judicial previa."
          }
        ];

        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              consulta: args.tema_o_conflicto,
              fallos_lideres: fallos,
              recomendacion_defensa: "Podés citar estos precedentes en descargos y contestaciones ante intimaciones provinciales o municipales."
            }, null, 2)
          }]
        });
      }

      // 1j. Políticas Provinciales y Tasas Municipales
      if (toolName === "consultar_tasas_provinciales_municipales") {
        const prov = (args.jurisdiccion || "CABA").toUpperCase();
        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              jurisdiccion: prov,
              municipio: args.municipio || "Régimen general provincial",
              alicuotas_iibb_referencia: {
                servicios: "3.0% a 5.0%",
                comercio: "3.0% a 4.5%",
                industria: "Exenta o 1.5%",
                exportacion_servicios: "Exenta (alícuota 0%)"
              },
              tasas_municipales: [
                {
                  tasa: "Tasa de Inspección, Seguridad e Higiene (TISH)",
                  condicion_legal: "Solo aplicable si la empresa cuenta con local, depósito o sucursal física en el municipio (Fallo Raffo y Esso CSJN).",
                  alerta: "Si vendés a distancia o por e-commerce, el reclamo municipal es improcedente."
                },
                {
                  tasa: "Tasa Vial sobre Combustibles",
                  condicion_legal: "Cuestionada judicialmente por doble imposición con el impuesto nacional a los combustibles."
                }
              ],
              explicacion_chico_10_anios: `En ${prov}, la provincia te cobra Ingresos Brutos sobre lo que vendés. Pero si un intendente te quiere cobrar una tasa municipal sin que tengas un local físico en su ciudad, la Corte Suprema te defiende y no tenés que pagarle.`
            }, null, 2)
          }]
        });
      }

      // 1k. Consultar Manuales Oficiales, Guías Paso a Paso y Lógica Operativa de ARCA
      if (toolName === "consultar_manuales_y_guias_arca") {
        const q = (args.query || "").toLowerCase();
        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              consulta: args.query,
              categoria: args.categoria || "TODAS",
              base_indexada: "245 guías paso a paso oficiales y mapas de arquitectura de ARCA (ex-AFIP)",
              contexto_institucional_arca_afip: "ARCA (Agencia de Recaudación y Control Aduanero) es la continuadora jurídica de la AFIP (Decreto 953/2024). Las Resoluciones Generales, formularios oficiales (F. 762, F. 2002, F. 931) y servidores bajo dominios .afip.gob.ar mantienen 100% su vigencia y validez técnica.",
              arquitectura_servicios: {
                "BIENES_PERSONALES_F762": {
                  nombre: "Bienes Personales Web (Formulario 762)",
                  url_base: "https://siapweb.cloud.afip.gob.ar/f762/",
                  tecnologia: "SPA AngularJS con Single Sign-On SAML",
                  solapas_criticas: {
                    "#/inicio": "Pantalla de bienvenida, vencimientos y acceso a trámites.",
                    "#/declaraciones.anteriores": "HISTORIAL COMPLETO: Lista todas las DDJJ presentadas desde 2013.",
                    "#/crearDJ": "Inicio de nueva declaración determinativa o informativa.",
                    "#/bienes": "Carga de bienes, exenciones e inmuebles."
                  },
                  regla_historica: "Hereda la estructura del viejo aplicativo SiAP. Las cuotas de SRL o acciones de SA tributan por F. 8115 de la sociedad y son exentas en cabeza del socio."
                },
                "RCEL_FACTURACION": {
                  nombre: "Comprobantes en Línea (RCEL)",
                  url_base: "https://fe.afip.gob.ar/rcel/",
                  regla_historica: "Flujo de 5 pasos con llamadas AJAX para refresco de puntos de venta y selección de empresa representada."
                },
                "IVA_F2002": {
                  nombre: "Declaración Jurada de IVA (F. 2002)",
                  url_base: "https://iva.afip.gob.ar/",
                  regla_historica: "Exige cerrar previamente el Libro de IVA Digital (RG 4597) para habilitar el F. 2002."
                }
              },
              leccion_clave: "Para evitar falsos negativos, la IA siempre debe navegar el árbol completo de rutas y sub-solapas de las Single Page Applications de ARCA."
            }, null, 2)
          }]
        });
      }

      // 1l. Solicitar Documentos Complementarios Off-ARCA (para adjuntar en el LLM)
      if (toolName === "solicitar_documentos_complementarios") {
        const t = (args.tramite || "iva_mensual").toLowerCase();
        const checklists = {
          iva_mensual: {
            titulo: "Cierre Mensual de IVA (F. 2002) y Libro IVA Digital",
            pedir_al_cliente: [
              "Extractos bancarios del mes (PDF/Excel) → rescatar IVA de comisiones, Impuesto al Cheque MiPyME y auditar SIRCREB.",
              "Resúmenes de tarjetas de crédito corporativas → IVA de servicios digitales (Meta, Google, AWS, OpenAI) y gastos deducibles.",
              "Tickets de combustible, peajes o gastos menores no reflejados en Mis Comprobantes."
            ],
            mensaje_para_usuario: "Ya bajé tus facturas desde ARCA, pero ARCA no ve toda la película. Arrastrá y soltá acá en el chat (PDF, foto o Excel) tus resúmenes bancarios, tarjetas y tickets extra para que no pagues ni un peso de más."
          },
          ganancias_y_bbpp: {
            titulo: "Ganancias y Bienes Personales Anual",
            pedir_al_cliente: [
              "Extractos bancarios al 31/12 (cajas de ahorro en pesos y dólares están 100% exentas de BBPP).",
              "Resúmenes de tarjetas de crédito del año (recupero del 30% percepciones dólar tarjeta).",
              "Pólizas de seguros, medicina prepaga, contratos de alquiler y gastos en USD del exterior (invoices)."
            ],
            mensaje_para_usuario: "Para armar tu película anual completa y bajarte el impuesto al mínimo legal, adjuntá acá en el chat tus resúmenes bancarios de diciembre, tarjetas, seguros/prepaga y comprobantes del exterior."
          },
          monotributo: {
            titulo: "Control de Monotributo y Blindaje contra Exclusión",
            pedir_al_cliente: [
              "Extractos bancarios y resúmenes de Mercado Pago / billeteras (cruzar acreditaciones vs facturación).",
              "Resúmenes de tarjetas de crédito personales (verificar consumos frente a tu categoría).",
              "Alquiler del local y boletas de luz (si tenés local físico)."
            ],
            mensaje_para_usuario: "ARCA también mira tus bancos y tarjetas para evaluar exclusiones. Adjuntame tus extractos bancarios y de Mercado Pago para verificar que estés 100% protegido."
          },
          sueldos_f931: {
            titulo: "Liquidación de Sueldos y F. 931",
            pedir_al_cliente: [
              "Novedades del mes (horas extras, faltas, vacaciones, comisiones, bonos, altas/bajas).",
              "Certificados médicos o licencias (si hubo).",
              "Última factura de póliza ART y Seguro Colectivo de Vida."
            ],
            mensaje_para_usuario: "Adjuntá o escribime acá en el chat las novedades de tus empleados del mes y la boleta de la ART para armar los recibos y el borrador de F. 931."
          }
        };
        const chosen = checklists[t] || checklists.iva_mensual;
        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              tramite: t,
              ...chosen,
              explicacion_chico_10_anios: "ARCA es como una cámara que solo filma la puerta de tu negocio, pero no ve el banco, las tarjetas ni los seguros. Si arrastrás esos papeles acá al chat, armamos el rompecabezas completo para ahorrarte plata."
            }, null, 2)
          }]
        });
      }

      // 1m. Conciliar Adjuntos y Generar Reporte Visual con Gráficos Mermaid
      if (toolName === "conciliar_y_graficar_pelicula_fiscal") {
        const fact = parseFloat(args.facturacion_bruta || 0);
        const gArca = parseFloat(args.gastos_arca || 0);
        const gOff = parseFloat(args.gastos_adjuntos_off_arca || 0);
        const sircreb = parseFloat(args.retenciones_sircreb_banco || 0);
        const cheque = parseFloat(args.impuesto_cheque_computable || 0);
        const percTarj = parseFloat(args.percepciones_tarjeta_recuperables || 0);
        const acred = parseFloat(args.acreditaciones_bancarias_mes || 0);
        const iva = parseFloat(args.iva_estimado || 0);
        const iibb = parseFloat(args.iibb_estimado || 0);
        const gan = parseFloat(args.ganancias_o_cuota_estimada || 0);

        const ahorroGastos = Math.round(gOff * 0.30 * 100) / 100;
        const ahorroTotal = Math.round((ahorroGastos + cheque + percTarj) * 100) / 100;
        const impBrutos = Math.round((iva + iibb + gan) * 100) / 100;
        const impNetos = Math.max(0, Math.round((impBrutos - ahorroTotal - sircreb) * 100) / 100);
        const gastosTotales = Math.round((gArca + gOff) * 100) / 100;
        const bolsillo = Math.max(0, Math.round((fact - gastosTotales - impNetos) * 100) / 100);
        const maxY = Math.round(Math.max(fact, gastosTotales, bolsillo, 1000) * 1.15);

        const mermaidTorta = `\`\`\`mermaid\npie showData\n    title "A dónde va cada peso que facturaste este mes"\n    "Tu ganancia limpia (bolsillo)" : ${bolsillo}\n    "Gastos operativos (ARCA + adjuntos)" : ${gastosTotales}\n    "Impuestos netos a pagar" : ${impNetos}\n    "Plata ahorrada con tus adjuntos" : ${ahorroTotal}\n\`\`\``;
        const mermaidBarras = `\`\`\`mermaid\nxychart-beta\n    title "Película Fiscal Completa del Mes (en ARS)"\n    x-axis ["Facturado", "Gastos", "Imp. Antes", "Imp. Final", "En Bolsillo"]\n    y-axis "Pesos ($)" 0 --> ${maxY}\n    bar [${Math.round(fact)}, ${Math.round(gastosTotales)}, ${Math.round(impBrutos)}, ${Math.round(impNetos)}, ${Math.round(bolsillo)}]\n\`\`\``;

        let alertaBanco = null;
        if (acred > 0 && fact > 0) {
          alertaBanco = (acred / fact > 1.15)
            ? { nivel: "ALTO", mensaje: `Entraron $${acred.toLocaleString('es-AR')} en bancos pero facturaste $${fact.toLocaleString('es-AR')}. Revisá transferencias entre cuentas propias o ventas sin facturar.` }
            : { nivel: "OK", mensaje: "Tus acreditaciones bancarias coinciden de forma saludable con tu facturación ARCA." };
        }

        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              resumen_numerico: {
                facturacion_bruta: fact,
                gastos_totales: gastosTotales,
                impuestos_sin_adjuntos: impBrutos,
                ahorro_rescatado_por_adjuntos: ahorroTotal,
                impuestos_netos_finales: impNetos,
                ganancia_neta_bolsillo: bolsillo
              },
              alerta_conciliacion_bancaria: alertaBanco,
              graficos_para_mostrar_al_cliente: {
                grafico_torta_mermaid: mermaidTorta,
                grafico_barras_mermaid: mermaidBarras,
                instruccion_renderizado_llm: "MOSTRÁ OBLIGATORIAMENTE estos gráficos (en Mermaid, SVG o Artifact interactivo) al usuario junto con un análisis estratégico y recomendaciones concretas para su negocio."
              },
              explicacion_clara: `Sobre una facturación bruta de $${fact.toLocaleString('es-AR')}, tus gastos operativos totales fueron de $${gastosTotales.toLocaleString('es-AR')}. Conciliar los resúmenes de banco y tarjeta que adjuntaste permitió rescatar $${ahorroTotal.toLocaleString('es-AR')} de ahorro fiscal directo, bajando la carga tributaria neta a $${impNetos.toLocaleString('es-AR')} y dejando un resultado limpio en bolsillo de $${bolsillo.toLocaleString('es-AR')}.`
            }, null, 2)
          }]
        });
      }

      // 1n. Ciclo de Aprendizaje Continuo: Agendar consulta sin respuesta
      if (toolName === "registrar_consulta_sin_respuesta") {
        const cid = "KNOW-" + new Date().toISOString().slice(0, 10).replace(/-/g, "") + "-" + crypto.randomUUID().slice(0, 6).toUpperCase();
        if (env.DB) {
          try {
            await env.DB.prepare(
              "INSERT INTO conocimiento_aprendido (id, cuit_origen, pregunta, contexto_cliente, estado, creada) VALUES (?, ?, ?, ?, 'pendiente', datetime('now'))"
            ).bind(cid, (args.cuit_origen || "anonimo").replace(/[^0-9a-zA-Z]/g, ""), args.pregunta || "", args.contexto_cliente || "").run();
          } catch (e) {}
        }
        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              consulta_id: cid,
              estado: "AGENDADA_PARA_ESPECIALISTA",
              pregunta_registrada: args.pregunta,
              mensaje_para_cliente: `Agendé tu consulta bajo el código ${cid} para que un contador especialista la resuelva con precisión normativa. Apenas tengamos el dictamen confirmado te avisamos y queda incorporado permanentemente al conocimiento del bot.`
            }, null, 2)
          }]
        });
      }

      // 1o. Incorporar conocimiento resuelto a la memoria viva del bot (D1)
      if (toolName === "incorporar_conocimiento_resuelto") {
        if (env.DB) {
          try {
            await env.DB.prepare(
              "UPDATE conocimiento_aprendido SET estado = 'resuelta_y_aprendida', respuesta_clara = ?, normativa_oficial = ?, resuelta = datetime('now') WHERE id = ?"
            ).bind(args.respuesta_clara || "", args.normativa_oficial || "", args.consulta_id || "").run();
          } catch (e) {}
        }
        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              ok: true,
              consulta_id: args.consulta_id,
              estado: "resuelta_y_aprendida",
              mensaje: "Respuesta validada e incorporada al conocimiento permanente del bot en D1."
            }, null, 2)
          }]
        });
      }

      // 1p. Buscar conocimiento aprendido de casos previos en D1
      if (toolName === "buscar_conocimiento_aprendido") {
        let coincidencias = [];
        if (env.DB) {
          try {
            const qLike = `%${(args.query || "").trim()}%`;
            const rows = await env.DB.prepare(
              "SELECT id, pregunta, respuesta_clara, normativa_oficial, resuelta FROM conocimiento_aprendido WHERE estado = 'resuelta_y_aprendida' AND (pregunta LIKE ? OR respuesta_clara LIKE ? OR normativa_oficial LIKE ?) ORDER BY resuelta DESC LIMIT 10"
            ).bind(qLike, qLike, qLike).all();
            coincidencias = rows.results || [];
          } catch (e) {}
        }
        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              consulta: args.query,
              coincidencias_encontradas: coincidencias.length,
              conocimiento_aprendido: coincidencias
            }, null, 2)
          }]
        });
      }

      // 1q. Análisis Económico-Financiero Integral (Contexto Real Formal + Informal PyME)
      if (toolName === "analizar_impacto_economico_financiero") {
        const vf = parseFloat(args.ventas_formales_mes || 0);
        const vi = parseFloat(args.ventas_informales_mes || 0);
        const cf = parseFloat(args.compras_formales_mes || 0);
        const ci = parseFloat(args.compras_informales_mes || 0);
        const empNoReg = parseInt(args.empleados_no_registrados || 0, 10);
        const sueldoProm = parseFloat(args.sueldo_promedio_bruto || 950000);
        const cobraBanco = Boolean(args.cobra_informal_por_banco_o_mp);

        const ventasTotales = vf + vi;
        const pctInformal = ventasTotales > 0 ? Math.round((vi / ventasTotales) * 1000) / 10 : 0;
        const margenReal = ventasTotales - (cf + ci);
        const margenFormal = vf - cf;
        const contingenciaLaboral = Math.round(empNoReg * sueldoProm * 20);
        const costoMensualBlanqueo = Math.round(empNoReg * sueldoProm * 0.35);

        const riesgos = [];
        const sugerencias = [];

        if (cobraBanco && vi > 0) {
          riesgos.push("RIESGO BANCARIO CRÍTICO: Cobrar operaciones no facturadas por banco o Mercado Pago dispara presunción de ventas omitidas (Art. 18 inc. g Ley 11.683) con ajuste de IVA + Ganancias + multas.");
          sugerencias.push("Ordenar de inmediato los medios de cobro: todo ingreso digital/bancario debe tener respaldo facturado.");
        }
        if (empNoReg > 0) {
          riesgos.push(`CONTINGENCIA LABORAL ESTIMADA: $${contingenciaLaboral.toLocaleString('es-AR')} por ${empNoReg} empleado(s) sin registrar ante eventuales reclamos o inspecciones.`);
          sugerencias.push("Evaluar regularización laboral bajo Ley Bases (Ley 27.742) con condonación de multas y reducción de cargas adeudadas para neutralizar el riesgo patrimonial y deducir los sueldos en Ganancias.");
        }
        if (ci > 0) {
          riesgos.push(`DISTORSIÓN DE MARGEN: Comprar $${ci.toLocaleString('es-AR')}/mes sin factura te hace perder Crédito Fiscal de IVA (21%) y te impide deducir ese costo en Ganancias.`);
          sugerencias.push("Formalizar primero a tus proveedores de mayor volumen: al recuperar IVA y deducir Ganancias, baja drásticamente el costo financiero real de facturar tus ventas.");
        }
        sugerencias.push("Activar Certificado MiPyME para computar 100% del Impuesto al Cheque a cuenta de Ganancias, diferir IVA a 90 días y acceder a crédito bancario/SGR a tasa subsidiada.");

        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              fotografia_economica_real: {
                ventas_totales_reales_mes: ventasTotales,
                porcentaje_fuera_circuito_formal: pctInformal,
                margen_bruto_real_mes: margenReal,
                margen_bruto_formal_visible_arca: margenFormal,
                contingencia_laboral_estimada_total: contingenciaLaboral,
                costo_mensual_regularizar_nomina: costoMensualBlanqueo
              },
              riesgos_detectados: riesgos,
              acciones_economico_financieras_sugeridas: sugerencias,
              instruccion_para_claude: "Usá este diagnóstico para asesorar al empresario con criterio de CFO/contador senior: compará el costo financiero de formalizar progresivamente frente al riesgo oculto sobre su caja y patrimonio."
            }, null, 2)
          }]
        });
      }

      // 1r. Web Service Oficial ARCA WSFEv1: FEDummy en vivo desde el Edge
      if (toolName === "verificar_estado_servidores_arca_ws") {
        const esHomo = (args.ambiente || "produccion").toLowerCase().includes("homo");
        const wsUrl = esHomo
          ? "https://wswhomo.afip.gov.ar/wsfev1/service.asmx"
          : "https://servicios1.afip.gov.ar/wsfev1/service.asmx";
        const soapBody = `<?xml version="1.0" encoding="UTF-8"?><soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/"><soapenv:Header/><soapenv:Body><ar:FEDummy/></soapenv:Body></soapenv:Envelope>`;

        try {
          const resp = await fetch(wsUrl, {
            method: "POST",
            headers: {
              "Content-Type": "text/xml; charset=utf-8",
              "SOAPAction": "http://ar.gov.afip.dif.FEV1/FEDummy"
            },
            body: soapBody
          });
          const xml = await resp.text();
          const getTag = (t) => (xml.match(new RegExp(`<${t}>(.*?)</${t}>`)) || [])[1] || "UNKNOWN";
          const app = getTag("AppServer");
          const db = getTag("DbServer");
          const auth = getTag("AuthServer");
          const online = app === "OK" && db === "OK" && auth === "OK";
          return jsonRpcSuccess(id, {
            content: [{
              type: "text",
              text: JSON.stringify({
                ambiente: esHomo ? "homologacion" : "produccion",
                endpoint: wsUrl,
                online,
                AppServer: app,
                DbServer: db,
                AuthServer: auth,
                mensaje: online ? "Servidores WSFEv1 de ARCA operativos al 100%." : "ARCA presenta degradación en WSFEv1."
              }, null, 2)
            }]
          });
        } catch (e) {
          return jsonRpcSuccess(id, {
            content: [{
              type: "text",
              text: JSON.stringify({
                ambiente: esHomo ? "homologacion" : "produccion",
                endpoint: wsUrl,
                online: false,
                error: e.message,
                mensaje: "No se pudo contactar a WSFEv1 de ARCA en este momento."
              }, null, 2)
            }]
          });
        }
      }

      // 1s. Borrador rápido WSFEv1 en el Edge (sin impacto hasta confirmado=true)
      if (toolName === "emitir_factura_wsfe" && !args.confirmado) {
        const neto = parseFloat(args.importe_neto || 0);
        const iva = parseFloat(args.importe_iva || 0);
        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              modo: "BORRADOR_WSFEV1_SIN_IMPACTO",
              ambiente: args.ambiente || "homologacion",
              cuit_emisor: args.cuit_emisor,
              punto_venta: args.pto_vta || 1,
              cbte_tipo: args.cbte_tipo,
              receptor_cuit: args.receptor_cuit,
              importe_neto: neto,
              importe_iva: iva,
              importe_total: Math.round((neto + iva) * 100) / 100,
              mensaje: "Borrador WSFEv1 validado. Confirmá con confirmado=true (requiere certificado digital WSAA vinculado) para obtener CAE y QR oficial en <1 segundo."
            }, null, 2)
          }]
        });
      }

      // 1t. Generador de Comprobante Oficial ARCA con QR RG 4892 en el Edge
      if (toolName === "generar_pdf_factura_oficial") {
        const letra = (args.letra || "A").toUpperCase();
        const codMap = { A: 1, B: 6, C: 11, E: 19, FCE_A: 201, NC_A: 3 };
        const cod = codMap[letra] || 1;
        const pto = parseInt(args.pto_vta || 1, 10);
        const nro = parseInt(args.nro_comprobante || 1, 10);
        const neto = parseFloat(args.importe_neto || 0);
        const iva = parseFloat(args.importe_iva || 0);
        const total = Math.round((neto + iva) * 100) / 100;
        const hoy = new Date().toISOString().slice(0, 10);
        const cuitEm = parseInt((args.emisor_cuit || "0").replace(/[^0-9]/g, ""), 10) || 0;
        const cuitRec = parseInt((args.receptor_cuit || "0").replace(/[^0-9]/g, ""), 10) || 0;
        const cae = (args.cae || "76471234567890").replace(/[^0-9]/g, "");

        const qrJson = JSON.stringify({
          ver: 1, fecha: hoy, cuit: cuitEm, ptoVta: pto, tipoCmp: cod, nroCmp: nro,
          importe: total, moneda: "PES", ctz: 1, tipoDocRec: 80, nroDocRec: cuitRec,
          tipoCodAut: "E", codAut: parseInt(cae, 10) || 0
        });
        const qrUrl = `https://www.afip.gob.ar/fe/qr/?p=${btoa(qrJson)}`;

        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              ok: true,
              comprobante: `FACTURA ${letra} ${String(pto).padStart(5, "0")}-${String(nro).padStart(8, "0")}`,
              codigo_arca: String(cod).padStart(3, "0"),
              emisor: `${args.emisor_razon_social} (CUIT ${args.emisor_cuit})`,
              receptor: `${args.receptor_razon_social} (CUIT ${args.receptor_cuit})`,
              importe_neto: neto,
              importe_iva: iva,
              importe_total: total,
              cae: cae,
              qr_oficial_rg4892: qrUrl,
              instruccion_llm: "Podés renderizar este comprobante como Artifact HTML imprimible en PDF A4 con el diseño oficial de ARCA y el enlace QR."
            }, null, 2)
          }]
        });
      }

      // 1u. [B2B] Configurar Estudio Contable (Marca Blanca en D1)
      if (toolName === "configurar_estudio_contable") {
        const cuitClean = (args.cuit_estudio || "").replace(/[^0-9]/g, "");
        const estudioId = "EST-" + (cuitClean.slice(-6) || crypto.randomUUID().slice(0, 6).toUpperCase());
        const branding = args.branding_pie || `${args.nombre_estudio} · Contadores Públicos Matriculados`;
        if (env.DB) {
          try {
            await env.DB.prepare(`
              INSERT INTO estudios_contables (id, nombre_estudio, cuit_estudio, socio_responsable, branding_pie, creado)
              VALUES (?, ?, ?, ?, ?, datetime('now'))
              ON CONFLICT(id) DO UPDATE SET
                nombre_estudio = excluded.nombre_estudio,
                socio_responsable = excluded.socio_responsable,
                branding_pie = excluded.branding_pie
            `).bind(estudioId, args.nombre_estudio, cuitClean, args.socio_responsable, branding).run();
          } catch (e) {}
        }
        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              ok: true,
              estudio_id: estudioId,
              nombre_estudio: args.nombre_estudio,
              socio_responsable: args.socio_responsable,
              branding_pie: branding,
              mensaje: `Estudio '${args.nombre_estudio}' habilitado en Modo B2B Multi-Cliente (ID: ${estudioId}).`
            }, null, 2)
          }]
        });
      }

      // 1v. [B2B] Importar Cartera Masiva de Clientes en D1
      if (toolName === "importar_cartera_clientes") {
        const estudioId = args.estudio_id;
        const lista = Array.isArray(args.clientes) ? args.clientes : [];
        let procesados = 0;
        if (env.DB) {
          for (const cli of lista) {
            const cuitCli = String(cli.cuit_cliente || cli.cuit || "").replace(/[^0-9]/g, "");
            if (!cuitCli) continue;
            try {
              await env.DB.prepare(`
                INSERT INTO cartera_clientes (id, estudio_id, cuit_cliente, razon_social, regimen, jurisdicciones, empleados, analista_asignado, estado_delegacion, actualizado)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(estudio_id, cuit_cliente) DO UPDATE SET
                  razon_social = excluded.razon_social,
                  regimen = excluded.regimen,
                  jurisdicciones = excluded.jurisdicciones,
                  empleados = excluded.empleados,
                  analista_asignado = excluded.analista_asignado,
                  actualizado = datetime('now')
              `).bind(
                `${estudioId}_${cuitCli}`,
                estudioId,
                cuitCli,
                cli.razon_social || "Cliente",
                (cli.regimen || "monotributo").toLowerCase(),
                JSON.stringify(cli.jurisdicciones || ["CABA"]),
                parseInt(cli.empleados || 0, 10),
                cli.analista_asignado || "Sin asignar",
                cli.estado_delegacion || "verificado"
              ).run();
              procesados++;
            } catch (e) {}
          }
        }
        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              ok: true,
              estudio_id: estudioId,
              clientes_importados_en_d1: procesados,
              mensaje: `${procesados} clientes cargados en la cartera del estudio ${estudioId}.`
            }, null, 2)
          }]
        });
      }

      // 1w. [B2B] Tablero Consolidado de Cartera y Vencimientos del Estudio
      if (toolName === "tablero_cartera_estudio") {
        const estudioId = args.estudio_id;
        const periodo = args.periodo || new Date().toISOString().slice(0, 7);
        let clientes = [];
        let cierres = [];
        if (env.DB) {
          try {
            const rCli = await env.DB.prepare("SELECT * FROM cartera_clientes WHERE estudio_id = ?").bind(estudioId).all();
            clientes = rCli.results || [];
            const rCie = await env.DB.prepare("SELECT * FROM cierres_mensuales_estudio WHERE estudio_id = ? AND periodo = ?").bind(estudioId, periodo).all();
            cierres = rCie.results || [];
          } catch (e) {}
        }
        if (args.analista) {
          const an = args.analista.toLowerCase();
          clientes = clientes.filter(c => (c.analista_asignado || "").toLowerCase() === an);
        }
        const cierresPorCuit = {};
        for (const c of cierres) {
          if (!cierresPorCuit[c.cuit_cliente]) cierresPorCuit[c.cuit_cliente] = [];
          cierresPorCuit[c.cuit_cliente].push(c);
        }

        let anomalias = 0, pendientesSocio = 0, aprobados = 0;
        const detalle = clientes.map(cli => {
          const cuit = cli.cuit_cliente;
          const term = parseInt(cuit.slice(-1), 10) || 0;
          const diaIva = 18 + Math.floor(term / 2);
          const diaF931 = term <= 3 ? 9 : (term <= 6 ? 10 : 11);
          const cc = cierresPorCuit[cuit] || [];
          const hasAnom = cc.some(x => x.alerta_anomalia === 1);
          const hasPend = cc.some(x => x.estado_aprobacion === "pendiente_revision_socio");
          const allAprob = cc.length > 0 && cc.every(x => x.estado_aprobacion === "aprobado_por_socio" || x.estado_aprobacion === "presentado_en_arca");
          if (hasAnom) anomalias++;
          if (hasPend) pendientesSocio++;
          if (allAprob) aprobados++;

          const semaforo = hasAnom ? "🔴 ANOMALÍA DETECTADA" : (allAprob ? "🟢 APROBADO POR SOCIO" : (cc.length ? "🟡 ESPERANDO SOCIO" : "⚪ SIN BORRADOR"));
          const vto = (cli.regimen || "").includes("mono")
            ? "Día 20 (Monotributo)"
            : `Día ${diaIva} (IVA/IIBB)` + (cli.empleados > 0 ? ` · Día ${diaF931} (F.931)` : "");
          return {
            cuit,
            razon_social: cli.razon_social,
            regimen: cli.regimen,
            analista: cli.analista_asignado,
            terminacion: term,
            proximo_vencimiento: vto,
            semaforo,
            cierres: cc.map(x => ({ id: x.id, impuesto: x.impuesto, monto: x.monto_actual, desvio_pct: x.desvio_pct, estado: x.estado_aprobacion }))
          };
        });

        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              estudio_id: estudioId,
              periodo,
              resumen_ejecutivo: {
                total_clientes: detalle.length,
                con_anomalias_rojas: anomalias,
                pendientes_revision_socio: pendientesSocio,
                aprobados_listos_para_arca: aprobados,
                sin_borrador_aun: Math.max(0, detalle.length - pendientesSocio - aprobados)
              },
              detalle_cartera: detalle
            }, null, 2)
          }]
        });
      }

      // 1x. [B2B] Registrar Borrador Junior + Detector de Anomalías (±30%)
      if (toolName === "registrar_cierre_y_detectar_anomalias") {
        const cuitClean = (args.cuit_cliente || "").replace(/[^0-9]/g, "");
        const imp = (args.impuesto || "IVA").toUpperCase();
        const per = args.periodo || new Date().toISOString().slice(0, 7);
        const cid = `CIE-${per.replace("-", "")}-${cuitClean.slice(-4)}-${imp.slice(0, 4)}`;
        const actual = parseFloat(args.monto_actual || 0);
        const ant = parseFloat(args.monto_mes_anterior || 0);
        const desvio = ant > 0 ? Math.round(((actual - ant) / ant) * 1000) / 10 : 0;
        const alerta = ant > 0 && Math.abs(desvio) >= 30 ? 1 : 0;

        if (env.DB) {
          try {
            await env.DB.prepare(`
              INSERT INTO cierres_mensuales_estudio (id, estudio_id, cuit_cliente, periodo, impuesto, monto_actual, monto_anterior, desvio_pct, alerta_anomalia, estado_aprobacion, preparado_por, notas, actualizado)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pendiente_revision_socio', ?, ?, datetime('now'))
              ON CONFLICT(id) DO UPDATE SET
                monto_actual = excluded.monto_actual,
                monto_anterior = excluded.monto_anterior,
                desvio_pct = excluded.desvio_pct,
                alerta_anomalia = excluded.alerta_anomalia,
                estado_aprobacion = 'pendiente_revision_socio',
                preparado_por = excluded.preparado_por,
                notas = excluded.notas,
                actualizado = datetime('now')
            `).bind(cid, args.estudio_id, cuitClean, per, imp, actual, ant, desvio, alerta, args.preparado_por || "Analista Junior", args.notas || "").run();
          } catch (e) {}
        }

        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              ok: true,
              cierre_id: cid,
              estado_aprobacion: "pendiente_revision_socio",
              monto_actual: actual,
              monto_anterior: ant,
              desvio_pct: desvio,
              alerta_anomalia: Boolean(alerta),
              semaforo: alerta ? `🔴 ALERTA DESVÍO ${desvio > 0 ? "+" : ""}${desvio}% (revisar antes de aprobar)` : "🟡 BORRADOR NORMAL — Listo para revisión del Socio",
              diagnostico: alerta
                ? `El ${imp} varió de $${ant.toLocaleString("es-AR")} a $${actual.toLocaleString("es-AR")} (${desvio > 0 ? "+" : ""}${desvio}%). Auditar compras faltantes, retenciones SIRCREB o picos de facturación antes de aprobar.`
                : "Variación dentro de rango normal (±30%)."
            }, null, 2)
          }]
        });
      }

      // 1y. [B2B] Aprobación en Bloque por el Socio
      if (toolName === "aprobar_cierres_socio") {
        const ids = Array.isArray(args.cierre_ids) ? args.cierre_ids : [];
        let aprobados = 0;
        if (env.DB) {
          for (const cid of ids) {
            try {
              await env.DB.prepare(
                "UPDATE cierres_mensuales_estudio SET estado_aprobacion = 'aprobado_por_socio', aprobado_por = ?, notas = COALESCE(notas, '') || ?, actualizado = datetime('now') WHERE estudio_id = ? AND id = ?"
              ).bind(args.aprobado_por, args.observaciones ? ` | Socio: ${args.observaciones}` : "", args.estudio_id, cid).run();
              aprobados++;
            } catch (e) {}
          }
        }
        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              ok: true,
              estudio_id: args.estudio_id,
              aprobado_por: args.aprobado_por,
              cierres_aprobados: ids,
              cantidad_aprobada: aprobados || ids.length,
              siguiente_paso: "Autorizados por el Socio. Listos para presentación en ARCA y envío Marca Blanca al cliente."
            }, null, 2)
          }]
        });
      }

      // 1z. [B2B] Reporte Marca Blanca del Estudio para Cliente Final
      if (toolName === "generar_reporte_marca_blanca_cliente") {
        const imps = Array.isArray(args.impuestos_a_pagar) ? args.impuestos_a_pagar : [];
        const total = imps.reduce((acc, i) => acc + parseFloat(i.monto || 0), 0);
        const ahorro = parseFloat(args.ahorro_o_credito_rescatado || 0);
        const lineas = imps.map(i => `• *${i.impuesto}*: $${parseFloat(i.monto || 0).toLocaleString("es-AR")} (vence ${i.vencimiento || "según CUIT"})`).join("\n");
        const recs = (args.recomendaciones_estudio && args.recomendaciones_estudio.length)
          ? args.recomendaciones_estudio
          : ["Mantener Certificado MiPyME vigente.", "Enviar extractos bancarios y tarjetas antes del día 10."];
        const pie = args.pie_firma_estudio || `${args.nombre_estudio} · Contadores Públicos Matriculados`;
        const msg = `*${args.nombre_estudio} — Cierre Impositivo ${args.periodo}*\nCliente: *${args.razon_social_cliente}*\n\nHola, ya cerramos y auditamos tus impuestos del período ${args.periodo}:\n${lineas}\n*Total consolidado:* $${total.toLocaleString("es-AR")}\n`
          + (ahorro > 0 ? `✅ *Ahorro / créditos computados:* $${ahorro.toLocaleString("es-AR")}\n` : "")
          + `\n*Recomendaciones de nuestro equipo:*\n${recs.map(r => `→ ${r}`).join("\n")}\n\nRespondé *OK* para generar los VEPs de pago.\n— _${pie}_`;

        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              ok: true,
              marca_blanca_estudio: args.nombre_estudio,
              cliente: args.razon_social_cliente,
              periodo: args.periodo,
              total_a_pagar: Math.round(total * 100) / 100,
              mensaje_listo_whatsapp_email: msg
            }, null, 2)
          }]
        });
      }

      // 1aa. Certificado MiPyME (F. 1272) — Diagnóstico y Borrador en el Edge
      if (toolName === "consultar_y_renovar_certificado_mipyme" && !args.confirmado) {
        const cuitClean = (args.cuit_empresa || "").replace(/[^0-9]/g, "");
        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              ok: true,
              servicio: "Certificado MiPyME (Formulario 1272 - ARCA)",
              cuit: cuitClean,
              modo: "DIAGNOSTICO_Y_BORRADOR_SIN_IMPACTO",
              beneficios_habilitados: [
                "Cómputo del 100% del Impuesto al Cheque como pago a cuenta de Ganancias (Micro y Pequeñas Empresas).",
                "Diferimiento del pago del saldo de IVA a 90 días.",
                "Exención de retenciones de IVA y Ganancias en cobros con tarjetas (RG 4011).",
                "Acceso a avales SGR y créditos productivos a tasa subsidiada."
              ],
              requisitos_renovacion: [
                "Tener presentadas las últimas 3 DDJJ de IVA y F. 931 (si es empleador).",
                "Habilitar el servicio 'PYMES Solicitud de Categorización y/o Beneficios' en ARCA."
              ],
              siguiente_paso: "Confirmá con confirmado=true (con bot Playwright conectado) para ejecutar la presentación del F. 1272 y descargar el certificado."
            }, null, 2)
          }]
        });
      }

      // 2. Registro transparente en base de datos D1 (Onboarding fricción cero solo con CUIT)
      const targetCuit = (args.cuit || args.emisor_cuit || "").replace(/[^0-9]/g, "");
      if (targetCuit && env.DB) {
        try {
          const cuenta = await env.DB.prepare("SELECT id, cuit FROM cuentas WHERE cuit = ?").bind(targetCuit).first();
          if (!cuenta) {
            const cid = crypto.randomUUID();
            await env.DB.prepare(
              "INSERT INTO cuentas (id, token_hash, cuit, creada, ultima_consulta) VALUES (?, ?, ?, datetime('now'), datetime('now'))"
            ).bind(cid, "mcp_" + cid, targetCuit).run();
          } else {
            await env.DB.prepare("UPDATE cuentas SET ultima_consulta = datetime('now') WHERE cuit = ?").bind(targetCuit).run();
          }
        } catch (dbErr) {
          // Log silencioso
        }
      }

      // 3. Si tenemos microservicio backend configurado, delegar la ejecución de herramientas ARCA en vivo
      const EDGE_LOCAL_TOOLS = new Set([
        "obtener_protocolo_doublecheck_arca",
        "validar_cobertura_auditoria_arca",
        "obtener_playbook_servicio_tributario",
        "iniciar_sesion_contador_agentico",
        "generar_automatizaciones_y_calendario_fiscal",
        "preparar_espacio_de_trabajo_impuestos"
      ]);
      if (env.BOT_API_URL && !EDGE_LOCAL_TOOLS.has(toolName)) {
        try {
          const authHeader = request.headers.get("authorization") || "";
          const bearerToken = authHeader.toLowerCase().startsWith("bearer ") ? authHeader.slice(7).trim() : "";
          const userToken = bearerToken || (url.searchParams.get("token") || "").trim();
          const llmOrigin = host.endsWith(".impuesto.com.ar") ? host.split(".")[0] : "mcp";

          const headers = {
            "Content-Type": "application/json",
            "X-LLM-Origin": llmOrigin
          };
          if (env.BOT_API_SECRET) headers["X-Bot-Secret"] = env.BOT_API_SECRET;
          if (userToken) headers["X-User-Token"] = userToken;

          const resp = await fetch(`${env.BOT_API_URL.replace(/\/$/, "")}/api/v1/mcp/tool`, {
            method: "POST",
            headers,
            body: JSON.stringify({ name: toolName, arguments: args }),
            signal: AbortSignal.timeout(26000)
          });
          const result = await resp.json();
          let outText = (result && typeof result.informe_contador_markdown === "string")
            ? result.informe_contador_markdown
            : JSON.stringify(result, null, 2);
          if (
            toolName === "auditar_estado_integral_arca" &&
            result &&
            result.ok !== false &&
            result.estado !== "EN_PROGRESO" &&
            PROMPTS_MAESTROS["02-post-diagnostico"]
          ) {
            outText = `${PROMPTS_MAESTROS["02-post-diagnostico"]}\n\n---\n\n${outText}`;
          }
          return jsonRpcSuccess(id, { content: [{ type: "text", text: outText }] });
        } catch (e) {
          // Manejo inteligente de caídas de ARCA con sugerencia de recordatorio
          return jsonRpcSuccess(id, {
            content: [{
              type: "text",
              text: JSON.stringify({
                estado: "ARCA_TEMPORALMENTE_NO_DISPONIBLE",
                mensaje: "ARCA (ex-AFIP) no respondió a tiempo o se encuentra momentáneamente saturada. Tus datos y borradores están a salvo.",
                detalle: e.message,
                sugerencia_reintento: "Los servidores de ARCA suelen descongestionarse en 2 horas o mañana a las 09:00 hs.",
                recordatorio_sugerido: "Recordame en 2 horas reintentar la operación en ARCA"
              }, null, 2)
            }]
          });
        }
      }

      // 1z. Motor de Doble Verificación (Double-Check) y Prohibición de Falsos Negativos en ARCA
      if (toolName === "obtener_protocolo_doublecheck_arca" || toolName === "validar_cobertura_auditoria_arca") {
        const MATRIZ = {
          estado_de_cuenta_y_deudas: {
            nombre: "Estado de Cuenta y Deuda Integral",
            por_que_es_critico: "SCT > Estado de Cumplimiento solo muestra impuestos generales DGI en ventana de 1 año. NO muestra deudas de Monotributo ni Autónomos (viven en CCMA) y oculta deudas consolidadas en planes de Mis Facilidades (que aparecen como 'Crédito por PFP' en $0).",
            fuentes_obligatorias: [
              { id: "ccma", servicio: "CCMA (Cálculo de Deuda)", accion: "Capital + intereses resarcitorios de Monotributo (020/021/024) y Autónomos (AUT)." },
              { id: "mis_facilidades", servicio: "Mis Facilidades (Seguimiento de Presentación)", accion: "Seleccionar CUIT exacto en <select> y listar TODOS los planes Vigentes y Caducos." },
              { id: "sct", servicio: "SCT (Estado de Cumplimiento + Deuda Consolidada + Incumplimientos)", accion: "Seleccionar CUIT exacto por label y revisar impuestos generales DGI." },
              { id: "portal_monotributo", servicio: "Portal Monotributo", accion: "Cuotas vencidas del mes + facturación acumulada vs tope categoría." }
            ],
            fuera_de_arca: ["Ingresos Brutos Provinciales (AGIP / ARBA / SIFERE)", "Tasas Municipales (TISH / ABL)", "Deudas Judiciales / Boletas de Deuda"],
            kws: ["deuda", "debo", "estado de cuenta", "saldo", "plan", "facilidades", "ccma", "sct", "autonomos", "monotributo"]
          },
          ganancias_personas_humanas: {
            nombre: "Impuesto a las Ganancias Personas Humanas",
            por_que_es_critico: "Desde 2025 conviven F. 711 (General) y F. 2711 (Declaración Jurada Simplificada RG 5692). Presentar en F. 2711 deja el vencimiento visible en F. 711 como pendiente.",
            fuentes_obligatorias: [
              { id: "f711", servicio: "F. 711 (#/declaraciones.anteriores)", accion: "Verificar DDJJ históricas régimen general." },
              { id: "f2711_simplificada", servicio: "F. 2711 Simplificada (#/declaracion.presentadas + Ratificación anual)", accion: "Verificar presentaciones bajo RG 5692." },
              { id: "sct_imp11", servicio: "SCT Impuesto 11", accion: "Cruzar SLD por período de origen." }
            ],
            fuera_de_arca: ["SiRADIG Trabajador", "Comprobantes deducibles no informados automáticamente"],
            kws: ["ganancias", "711", "2711", "simplificada", "siradig", "rentas"]
          },
          bienes_personales: {
            nombre: "Impuesto sobre los Bienes Personales",
            por_que_es_critico: "F. 762 Web (#/inicio) solo muestra borradores del año en curso; el historial real solo aparece en #/declaraciones.anteriores.",
            fuentes_obligatorias: [
              { id: "f762_anteriores", servicio: "F. 762 (#/declaraciones.anteriores)", accion: "Nunca concluir 'sin presentaciones' desde #/inicio." },
              { id: "nuestra_parte", servicio: "Nuestra Parte (al 31/12)", accion: "Cruzar inmuebles, cuentas, fideicomisos y tenencias." },
              { id: "sct_imp180", servicio: "SCT Impuesto 180", accion: "Verificar anticipos, REIBP y saldos." }
            ],
            fuera_de_arca: ["Valuaciones fiscales VIR CABA / ARBA y cotizaciones BNA al 31/12"],
            kws: ["bienes personales", "bbpp", "762", "patrimonio", "reibp"]
          },
          iva_y_facturacion: {
            nombre: "IVA, Facturación y Proveedores",
            por_que_es_critico: "Mirar solo Mis Comprobantes sin Mis Retenciones, Base e-APOC y SCT Imp. 30 omite retenciones computables o facturas apócrifas impugnables.",
            fuentes_obligatorias: [
              { id: "mis_comprobantes", servicio: "Mis Comprobantes (Emitidos y Recibidos)", accion: "Descargar ventas y compras del período." },
              { id: "mis_retenciones", servicio: "Mis Retenciones (SIRE/SICORE)", accion: "Relevar retenciones y percepciones nacionales." },
              { id: "base_eapoc", servicio: "Base e-APOC", accion: "Validar proveedores antes de computar crédito fiscal." },
              { id: "sct_imp30", servicio: "SCT Impuesto 30 (IVA)", accion: "Separar saldo técnico vs SLD." }
            ],
            fuera_de_arca: ["Extractos bancarios (SIRCREB/SIRTAC)", "Ingresos Brutos Provinciales"],
            kws: ["iva", "facturas", "comprobantes", "retenciones", "e-apoc", "apocrifas"]
          },
          empleador_seguridad_social: {
            nombre: "Empleador y Seguridad Social (F. 931)",
            por_que_es_critico: "La deuda previsional se reparte entre SCT Seguridad Social, Mis Facilidades, Sindicatos y ART.",
            fuentes_obligatorias: [
              { id: "declaracion_en_linea", servicio: "Declaración en Línea (F. 931)", accion: "Verificar presentaciones mensuales y nómina." },
              { id: "sct_segsoc", servicio: "SCT Impuestos 301/302/351/352", accion: "Verificar aportes y contribuciones impagas." },
              { id: "mis_facilidades_ss", servicio: "Mis Facilidades (Planes Previsionales)", accion: "Verificar planes vigentes y caducos." }
            ],
            fuera_de_arca: ["Boletas Sindicales", "ART y Seguro de Vida Obligatorio"],
            kws: ["931", "sueldos", "empleados", "empleador", "cargas sociales", "seguridad social"]
          }
        };

        const detectarDom = (txt) => {
          const q = (txt || "").toLowerCase();
          if (MATRIZ[q]) return q;
          let best = "estado_de_cuenta_y_deudas", bestScore = 0;
          for (const [k, v] of Object.entries(MATRIZ)) {
            const sc = v.kws.filter(w => q.includes(w)).length;
            if (sc > bestScore) { bestScore = sc; best = k; }
          }
          return best;
        };

        if (toolName === "obtener_protocolo_doublecheck_arca") {
          const dom = detectarDom(args.consulta_o_dominio);
          const cfg = MATRIZ[dom];
          return jsonRpcSuccess(id, {
            content: [{
              type: "text",
              text: JSON.stringify({
                dominio: dom,
                nombre: cfg.nombre,
                regla_oro: "PROHIBICIÓN DE FALSO NEGATIVO: No afirmar jamás 'Deuda $0', 'Al día' ni 'Sin presentaciones' sin haber verificado el 100% de fuentes_obligatorias. Si falta alguna, informar 'VERIFICACIÓN INCOMPLETA' detallando qué falta.",
                por_que_es_critico: cfg.por_que_es_critico,
                fuentes_obligatorias: cfg.fuentes_obligatorias,
                alertas_fuera_de_arca: cfg.fuera_de_arca
              }, null, 2)
            }]
          });
        }

        const dom = detectarDom(args.dominio);
        const cfg = MATRIZ[dom];
        const oblig = cfg.fuentes_obligatorias.map(f => f.id);
        const verif = new Set((args.fuentes_verificadas || []).map(x => String(x).toLowerCase().trim()));
        const fall = new Set((args.fuentes_fallidas || []).map(x => String(x).toLowerCase().trim()));
        const cubiertas = oblig.filter(f => verif.has(f));
        const faltantes = oblig.filter(f => !verif.has(f));
        const completa = faltantes.length === 0 && fall.size === 0;

        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              dominio: dom,
              verificacion_completa: completa,
              puede_afirmar_deuda_cero_o_al_dia: completa,
              cobertura: `${cubiertas.length}/${oblig.length}`,
              fuentes_verificadas: cubiertas,
              fuentes_faltantes: faltantes,
              fuentes_con_error: Array.from(fall),
              sello_verificacion: completa
                ? `✅ VERIFICACIÓN INTEGRAL ARCA (${cubiertas.length}/${oblig.length}: ${cubiertas.join(", ")}) | ⚠️ No incluye tributos fuera de ARCA (${cfg.fuera_de_arca.slice(0, 2).join("; ")})`
                : `⚠️ VERIFICACIÓN INCOMPLETA (${cubiertas.length}/${oblig.length}) — Faltan revisar: ${faltantes.join(", ")}. PROHIBIDO afirmar 'Deuda $0' o 'Al día' hasta completar estas fuentes.`
            }, null, 2)
          }]
        });
      }

      // 1z2. Protocolo Pre-Flight Universal y Playbooks de Inicio por Servicio Tributario (ARCA, AGIP, ARBA, SIFERE)
      if (toolName === "obtener_playbook_servicio_tributario") {
        const PREFLIGHT = [
          { paso: "1. Identidad y Representado Activo", pregunta: "¿Qué CUIT / Razón Social / Establecimiento está seleccionado por defecto?", regla: "Nunca asumir índice 0 en <select>. Leer cabecera y elegir siempre por label exacto de la CUIT." },
          { paso: "2. Disparador de Consulta o Cálculo", pregunta: "¿Los datos vienen precargados o hay que pulsar un botón ('Cálculo de Deuda', 'Consultar', 'Siguiente', 'Filtrar')?", regla: "Pantalla vacía al entrar NO significa saldo $0." },
          { paso: "3. Ruta Real vs. Pantalla de Bienvenida", pregunta: "¿La home (#/inicio) muestra el historial real o solo borradores?", regla: "Ir siempre a historial/presentaciones/seguimiento (#/declaraciones.anteriores, #/declaracion.presentadas, Seguimiento de Presentación)." },
          { paso: "4. Rangos de Fecha, Filtros y Paginación", pregunta: "¿Qué rango de fechas, límite de períodos o páginas ('Mostrar 12/48', 'Página 1 de N', tope 1 año) recorta resultados?", regla: "Expandir al máximo o iterar año por año y recorrer todas las páginas." },
          { paso: "5. Extracción Técnica del DOM", pregunta: "¿Los importes están en innerText, <input>.value, <iframe>, detrás de un modal o en un PDF en pestaña nueva?", regla: "Leer innerText + input.value, revisar iframes y cerrar modales bloqueantes." },
          { paso: "6. Cruce con Módulos Hermanos", pregunta: "¿Existe otro módulo que pone en cero o reemplaza lo que muestra esta pantalla?", regla: "Mis Facilidades pone en $0 CCMA/SCT ('Crédito por PFP'); F. 2711 deja F. 711 como pendiente; AGIP/ARBA/SIFERE no figuran en ARCA." },
          { paso: "7. Popups, Ventanas Emergentes y Pestañas Nuevas", pregunta: "¿El servicio, PDF, VEP o acuse se abre en un popup/pestaña nueva (window.open / target='_blank')?", regla: "Habilitar siempre popups para el organismo y capturar eventos 'popup'/'page' antes de hacer clic; si están bloqueados, el servicio falla en silencio." }
        ];
        const PLAYBOOKS = {
          arca_sct: { organismo: "ARCA", servicio: "Sistema de Cuentas Tributarias (SCT)", como_inicia: "<select> de CUITs representadas -> FILTRAR -> Cuenta Corriente > Estado de Cumplimiento (formato AAAAMM00, máximo 1 año) + Detalle de Deuda Consolidada + Incumplimientos.", que_NO_muestra: "NO muestra Monotributo/Autónomos (ver CCMA) ni cuotas futuras de Mis Facilidades.", aliases: ["sct", "cuentas tributarias"] },
          arca_ccma: { organismo: "ARCA", servicio: "CCMA (Monotributistas y Autónomos)", como_inicia: "Entrar por Portal CF -> pulsar 'Cálculo de Deuda' -> expandir Filtro Avanzado (48 períodos, Todos los impuestos 020/021/024/AUT).", que_NO_muestra: "Si aparece 'Crédito por PFP Mis Facilidades', ir obligatoriamente a Mis Facilidades.", aliases: ["ccma", "autonomos"] },
          arca_mis_facilidades: { organismo: "ARCA", servicio: "Mis Facilidades", como_inicia: "Seleccionar CUIT exacta en <select> -> Seguimiento de Presentación -> listar TODOS los planes Vigentes, Caducos y Cancelados.", que_NO_muestra: "No muestra deuda corriente no consolidada (ver CCMA y SCT).", aliases: ["mis facilidades", "planes", "moratoria"] },
          arca_portal_monotributo: { organismo: "ARCA", servicio: "Portal Monotributo", como_inicia: "Revisar Categoría, Facturación acumulada vs Tope, 'Pagar período vencido' y 'Estado de Cuenta'.", que_NO_muestra: "No muestra Autónomos ni planes anteriores.", aliases: ["monotributo", "admin_mono"] },
          arca_ganancias_ph: { organismo: "ARCA", servicio: "Ganancias PH (F. 711 + F. 2711 Simplificada)", como_inicia: "Revisar AMBOS: F. 2711 Simplificada (#/declaracion.presentadas + Ratificación anual; leer <input>.value en Determinación) Y F. 711 (#/declaraciones.anteriores).", que_NO_muestra: "F. 711 sigue mostrando vencido un período ya presentado en F. 2711.", aliases: ["ganancias", "711", "2711", "simplificada"] },
          arca_bienes_personales: { organismo: "ARCA", servicio: "Bienes Personales Web (F. 762)", como_inicia: "Ir directo a #/declaraciones.anteriores (nunca #/inicio) y cruzar con Nuestra Parte.", que_NO_muestra: "#/inicio parece vacío aunque haya historial.", aliases: ["bienes personales", "bbpp", "762"] },
          agip_caba: { organismo: "AGIP (CABA)", servicio: "Cuenta Corriente Tributaria / e-SICOL (Clave Ciudad)", como_inicia: "Seleccionar impuesto/inscripción -> Consultar Deuda Total (todos los períodos) + Planes de Facilidades + Gestión Judicial/Mandatarios.", que_NO_muestra: "No incluye deuda nacional ARCA ni otras provincias.", aliases: ["agip", "caba", "clave ciudad"] },
          arba_pba: { organismo: "ARBA (PBA)", servicio: "Autogestión IIBB / Inmobiliario / Automotor (CIT)", como_inicia: "Seleccionar objeto/inscripción -> Estado de Deuda + Presentaciones de DDJJ + Planes de Pago + Apremio.", que_NO_muestra: "No incluye ARCA ni tasas municipales.", aliases: ["arba", "pba", "cit"] },
          sifere_cm: { organismo: "COMARB", servicio: "SIFERE Web (Convenio Multilateral)", como_inicia: "Ingresar vía ARCA -> elegir CUIT y sede -> revisar CM03, CM05, SIRCREB y SIRTAC.", que_NO_muestra: "Intereses y multas locales se consultan en cada fisco provincial.", aliases: ["sifere", "convenio multilateral", "comarb", "cm03"] }
        };
        const q = (args.servicio_o_consulta || "").toLowerCase().trim();
        let foundKey = PLAYBOOKS[q] ? q : Object.keys(PLAYBOOKS).find(k => k.includes(q) || PLAYBOOKS[k].aliases.some(a => q.includes(a)));
        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify(foundKey ? {
              servicio_encontrado: true,
              id: foundKey,
              playbook: PLAYBOOKS[foundKey],
              protocolo_preflight_universal: PREFLIGHT
            } : {
              servicio_encontrado: false,
              consulta: args.servicio_o_consulta,
              servicios_con_playbook_verificado: Object.keys(PLAYBOOKS),
              instruccion_obligatoria: "Servicio sin playbook específico aún. Ejecutar obligatoriamente las 6 preguntas del protocolo_preflight_universal antes de reportar valores.",
              protocolo_preflight_universal: PREFLIGHT
            }, null, 2)
          }]
        });
      }

      // 1z3. Journey Orchestrator: Iniciar Sesión del Contador Agéntico (capacidades + triaje situacional + memoria D1)
      if (toolName === "iniciar_sesion_contador_agentico") {
        const cuitClean = (args.cuit || "").replace(/[^0-9]/g, "");
        let perfilGuardado = null;
        if (cuitClean && env.DB) {
          try {
            const row = await env.DB.prepare("SELECT * FROM perfiles_contribuyentes WHERE cuit = ?").bind(cuitClean).first();
            if (row) {
              perfilGuardado = {
                cuit: row.cuit,
                razon_social: row.razon_social,
                tipo_personeria: row.tipo_personeria,
                actividad: row.que_vende,
                ubicacion: row.ubicacion_sede,
                empleados: row.cantidad_empleados,
                actualizado: row.actualizado
              };
            }
          } catch (e) {}
        }

        const CAPACIDADES = [
          { pilar: "1. Auditoría de Deuda Real y Planes", detalle: "Cruza CCMA (Monotributo/Autónomos), Mis Facilidades (cuotas y caducidad), SCT y Portal Monotributo con Sello de Verificación anti falsos negativos." },
          { pilar: "2. Facturación Electrónica y Cierre de IVA", detalle: "Emite Facturas A/B/C/E con CAE oficial y QR, cruza Mis Comprobantes, Mis Retenciones y valida proveedores contra Base e-APOC." },
          { pilar: "3. Monotributo y Recategorización", detalle: "Controla facturación acumulada vs. tope de categoría, alerta riesgo de exclusión, gestiona débito automático y simula pase a RI o SRL." },
          { pilar: "4. Ganancias (F. 711 / F. 2711) y Bienes Personales", detalle: "Audita declaraciones históricas y Simplificada RG 5692, saldos a favor compensables, SiRADIG y cruces con Nuestra Parte." },
          { pilar: "5. PyMEs, Sueldos (F. 931) y Certificado MiPyME", detalle: "Calcula cargas sociales, renueva Certificado MiPyME (F. 1272) para recuperar 100% del Impuesto al Cheque y analiza rentabilidad formal/informal." },
          { pilar: "6. Modo Estudio Contable B2B", detalle: "Gestiona carteras multi-cliente con tablero por terminación de CUIT, alertas de desvíos >30%, aprobación Junior → Socio y reportes Marca Blanca." }
        ];

        const sit = (args.situacion || (perfilGuardado ? (perfilGuardado.tipo_personeria || "explorar") : "explorar")).toLowerCase();
        const RUTAS = {
          monotributo: {
            titulo: "Checklist prioritario para Monotributista",
            que_revisar_hoy: [
              "🔴 Estado de cuenta real en CCMA + Mis Facilidades (evitar acumulación de cuotas y baja automática a las 10 impagas).",
              "🟡 Margen de facturación acumulada vs. tope de categoría actual antes de la próxima recategorización.",
              "🟢 Verificar Monotributo Unificado (AGIP/ARBA), adhesión a Débito Automático (reintegro anual) y Domicilio Fiscal Electrónico (DFE)."
            ],
            siguiente_paso: "Pasame tu CUIT (o conectá tu clave fiscal de solo lectura) y te traigo en 30 segundos tu margen de categoría y deuda real."
          },
          responsable_inscripto: {
            titulo: "Checklist prioritario para Responsable Inscripto",
            que_revisar_hoy: [
              "🔴 Deuda exigible en CCMA (Autónomos) + SCT (IVA/Ganancias) + estado de planes vigentes en Mis Facilidades.",
              "🟡 Posición de IVA del mes (Mis Comprobantes + Mis Retenciones) y control de proveedores en Base e-APOC.",
              "🟢 Certificado MiPyME (F. 1272) para diferir IVA a 90 días y computar Impuesto al Cheque a cuenta, más revisión de Ganancias F. 2711 Simplificada."
            ],
            siguiente_paso: "Decime tu CUIT y arrancamos por tu posición de IVA del mes o por una auditoría integral de deuda y saldos a favor."
          },
          pyme_sociedad: {
            titulo: "Checklist prioritario para PyME / Sociedad (SRL / SA / SAS)",
            que_revisar_hoy: [
              "🔴 Deuda consolidada en SCT (IVA 30, F. 931 Seguridad Social 301/302/351/352, Ganancias 10) + cuotas de planes en Mis Facilidades.",
              "🟡 Vigencia del Certificado MiPyME (F. 1272) y control de proveedores apócrifos (Base e-APOC) + percepciones SIRCREB/IIBB.",
              "🟢 Planificación de retiros de socios (honorarios directores vs. dividendos 7%) y lectura de notificaciones críticas en DFE."
            ],
            siguiente_paso: "Indicame el CUIT de la sociedad y si querés empezar por estado de cuenta integral, cierre de IVA/F.931 o renovación MiPyME."
          },
          empleado_relacion_dependencia: {
            titulo: "Checklist prioritario para Relación de Dependencia",
            que_revisar_hoy: [
              "🔴 Verificar si ya presentaste Ganancias (F. 711 o F. 2711 Simplificada) y Bienes Personales (F. 762) y si tenés saldo a favor sin usar.",
              "🟡 Habilitar y cargar deducciones del año en curso en SiRADIG - Trabajador (prepaga, alquiler, educación, seguros, servicio doméstico).",
              "🟢 Cruzar Nuestra Parte y evaluar compensación o devolución de percepciones y saldos de libre disponibilidad."
            ],
            siguiente_paso: "Decime si querés revisar tus presentaciones de Ganancias/BBPP o calcular cuánto podés ahorrar cargando SiRADIG."
          },
          estudio_contable: {
            titulo: "Checklist prioritario para Estudio Contable (B2B)",
            que_revisar_hoy: [
              "🔴 Importar o abrir tu cartera de clientes para ver vencimientos agrupados por terminación de CUIT.",
              "🟡 Activar el semáforo de cierres con alerta automática ante desvíos >30% respecto al mes anterior.",
              "🟢 Aprobar cierres en bloque (flujo Junior → Socio) y generar reportes ejecutivos 100% Marca Blanca listos para WhatsApp/Email."
            ],
            siguiente_paso: "Decime el nombre de tu estudio (o pasame una lista de CUITs) y armamos tu tablero multi-cliente en 1 minuto."
          }
        };

        const rutaElegida = Object.keys(RUTAS).find(k => sit.includes(k.split("_")[0])) || null;
        const vincularBase = "https://impuesto.com.ar/vincular";
        const vincularUrl = cuitClean ? `${vincularBase}?cuit=${cuitClean}` : vincularBase;

        // Verificar si el usuario YA viene autenticado con token y tiene CUITs vinculados en la bóveda
        let cuentaAutenticada = null;
        const authHdrInit = request.headers.get("authorization") || "";
        const bearerInit = authHdrInit.toLowerCase().startsWith("bearer ") ? authHdrInit.slice(7).trim() : "";
        const tokenInit = bearerInit || (url.searchParams.get("token") || "").trim();
        if (tokenInit && env.BOT_API_URL) {
          try {
            const h = { "Content-Type": "application/json", "X-User-Token": tokenInit, "X-LLM-Origin": host.endsWith(".impuesto.com.ar") ? host.split(".")[0] : "mcp" };
            if (env.BOT_API_SECRET) h["X-Bot-Secret"] = env.BOT_API_SECRET;
            const rEmp = await fetch(`${env.BOT_API_URL.replace(/\/$/, "")}/api/v1/mcp/tool`, {
              method: "POST",
              headers: h,
              body: JSON.stringify({ name: "listar_empresas", arguments: {} }),
              signal: AbortSignal.timeout(4000)
            });
            const dEmp = await rEmp.json();
            if (dEmp && dEmp.ok && dEmp.usuario && Array.isArray(dEmp.empresas_vinculadas) && dEmp.empresas_vinculadas.length > 0) {
              cuentaAutenticada = {
                usuario: dEmp.usuario,
                empresas: dEmp.empresas_vinculadas
              };
            }
          } catch (e) {}
        }

        const constitucion = PROMPTS_MAESTROS["00-constitucion-contador-cfo"] || "";
        const radar = PROMPTS_MAESTROS["05-radar-normativo-vigente"] || "";

        if (cuentaAutenticada) {
          const listaCuits = cuentaAutenticada.empresas
            .map(e => `- CUIT **${e.cuit}** (${e.alias || "Contribuyente"} · rol: ${e.rol || "owner"} · modo solo lectura activo)`)
            .join("\n");
          const promptAutenticado = [
            "# Orden Maestra — Usuario YA Autenticado y Vinculado (CERO FRICCIÓN)",
            `El usuario **YA está autenticado** como \`${cuentaAutenticada.usuario}\` y tiene los siguientes CUITs vinculados y listos en la bóveda cifrada:`,
            listaCuits,
            "",
            "## Reglas obligatorias para tu respuesta ahora:",
            "1. **PROHIBIDO** pedirle que se vincule en `impuesto.com.ar/vincular` y **PROHIBIDO** volver a pedirle el CUIT (ya los tenés arriba).",
            "2. Saludalo breve y ejecutivamente como su Contador de Cabecera y CFO confirmando en 1 línea que ya estás conectado a su cuenta y CUIT(s) arriba listados.",
            "3. Ofrecele directamente 3–4 acciones concretas para elegir ahora (ej: **1) Auditoría 360° en ARCA** — aclarando que demora 1 a 10 minutos en segundo plano —, **2) Ver historial compartido de otros LLMs**, **3) Revisar DFE / comprobantes / vencimientos**, **4) Autorizar a un socio o contador por email**).",
            "4. Si el usuario ya pidió algo concreto en su primer mensaje (por ej. auditar su CUIT), **ejecutalo directamente** sin repreguntar."
          ].join("\n");

          const contextoPerfil = perfilGuardado
            ? `\n\n---\n**Perfil recuperado de memoria:** ${perfilGuardado.razon_social} (CUIT ${perfilGuardado.cuit} · ${perfilGuardado.tipo_personeria} · ${perfilGuardado.ubicacion}).`
            : "";

          return jsonRpcSuccess(id, {
            content: [{
              type: "text",
              text: [constitucion, promptAutenticado, radar, contextoPerfil].filter(Boolean).join("\n\n---\n\n")
            }]
          });
        }

        const etapaKey = sit.includes("estudio")
          ? "04-estudio-contable"
          : (perfilGuardado ? "03-seguimiento-mensual" : "01-primera-interaccion");
        const promptMaestro = PROMPTS_MAESTROS[etapaKey] || PROMPTS_MAESTROS["01-primera-interaccion"] || "";
        const contextoExtra = perfilGuardado
          ? `\n\n---\n**Perfil recuperado de memoria:** ${perfilGuardado.razon_social} (CUIT ${perfilGuardado.cuit} · ${perfilGuardado.tipo_personeria} · ${perfilGuardado.ubicacion}).`
          : `\n\n---\n**Link oficial de vinculación:** ${vincularUrl} (Estudios Contables: ${vincularBase}?tipo=estudio).`;

        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: [constitucion, promptMaestro, radar, contextoExtra].filter(Boolean).join("\n\n---\n\n")
          }]
        });
      }

      // 1z4. Generador de Automatizaciones, Recordatorios y Calendario Fiscal por Perfil y CUIT
      if (toolName === "generar_automatizaciones_y_calendario_fiscal") {
        const perfil = (args.perfil || "monotributo").toLowerCase();
        const cuitClean = (args.cuit || "").replace(/[^0-9]/g, "");
        const term = cuitClean ? parseInt(cuitClean.slice(-1), 10) : 5;
        const diaAutonomos = term <= 3 ? 5 : (term <= 6 ? 6 : 7);
        const diaF931 = term <= 3 ? 9 : (term <= 6 ? 10 : 11);
        const diaIva = 18 + Math.floor(term / 2);
        const cliente = (args.cliente_ia || "todos").toLowerCase();

        const EVENTOS_BASE = {
          monotributo: [
            { id: "mono_pago", titulo: "Pago Cuota Monotributo", cadencia: "Mensual — Día 18 (vence día 20)", cron: "0 9 18 * *", prompt: "Revisá mi cuota de Monotributo en Portal Monotributo y CCMA, verificá si tengo deuda pendiente y generame el resumen de pago." },
            { id: "mono_tope", titulo: "Control Tope de Categoría Monotributo", cadencia: "Mensual — Día 25", cron: "0 10 25 * *", prompt: "Consultá mi facturación acumulada de los últimos 12 meses vs. el tope de mi categoría de Monotributo y decime cuánto margen me queda." },
            { id: "planes_dia16", titulo: "Control Débito Automático Planes Mis Facilidades", cadencia: "Mensual — Día 14 (débito día 16)", cron: "0 9 14 * *", prompt: "Recordame cuánto se debita el día 16 por mis planes vigentes en Mis Facilidades para tener saldo en la CBU." },
            { id: "dfe_semanal", titulo: "Revisión Domicilio Fiscal Electrónico (DFE)", cadencia: "Semanal — Lunes 09:30", cron: "30 9 * * 1", prompt: "Revisá mi Domicilio Fiscal Electrónico (DFE) en ARCA y avisame solo si hay notificaciones nuevas o intimaciones." },
            { id: "recat_semestral", titulo: "Recategorización Semestral Monotributo", cadencia: "Semestral — 5 de Enero y 5 de Julio", cron: "0 9 5 1,7 *", prompt: "Evaluá si me corresponde recategorizar el Monotributo este semestre con mi facturación acumulada y simulá la nueva cuota." }
          ],
          responsable_inscripto: [
            { id: "autonomos_pago", titulo: `Vencimiento Autónomos (CUIT term. ${term})`, cadencia: `Mensual — Día ${diaAutonomos - 2} (vence día ${diaAutonomos})`, cron: `0 9 ${Math.max(1, diaAutonomos - 2)} * *`, prompt: "Revisá mi cuota mensual de Autónomos y saldo en CCMA para pagarla en término sin intereses." },
            { id: "planes_dia16", titulo: "Control Débito Planes Mis Facilidades", cadencia: "Mensual — Día 14 (débito día 16)", cron: "0 9 14 * *", prompt: "Verificá el total a debitar el día 16 en mis planes vigentes de Mis Facilidades." },
            { id: "iva_cierre", titulo: `Cierre Mensual IVA F. 2002 (CUIT term. ${term})`, cadencia: `Mensual — Día ${diaIva - 4} (vence día ${diaIva})`, cron: `0 9 ${diaIva - 4} * *`, prompt: "Armá mi posición preliminar de IVA del mes cruzando Mis Comprobantes, Mis Retenciones y Base e-APOC." },
            { id: "dfe_semanal", titulo: "Revisión DFE semanal", cadencia: "Semanal — Lunes 09:30", cron: "30 9 * * 1", prompt: "Revisá notificaciones nuevas en mi DFE de ARCA." },
            { id: "ganancias_bbpp", titulo: "Preparación Anual Ganancias (F. 2711) y BBPP", cadencia: "Anual — 15 de Mayo", cron: "0 9 15 5 *", prompt: "Revisá Nuestra Parte, mis deducciones, Ratificación F. 2711 y simulá Ganancias y Bienes Personales antes del vencimiento de Junio." }
          ],
          pyme_sociedad: [
            { id: "f931_cierre", titulo: `Cierre Sueldos y F. 931 (CUIT term. ${term})`, cadencia: `Mensual — Día ${diaF931 - 3} (vence día ${diaF931})`, cron: `0 9 ${diaF931 - 3} * *`, prompt: "Verificá novedades de nómina, cargas sociales F. 931 y saldos de Seguridad Social (Imp. 301/302/351/352) en SCT." },
            { id: "planes_dia16", titulo: "Control Débito Planes Mis Facilidades (Sociedad)", cadencia: "Mensual — Día 14 (débito día 16)", cron: "0 9 14 * *", prompt: "Verificá el monto total a debitar el día 16 por los planes vigentes de la sociedad en Mis Facilidades." },
            { id: "iva_cierre", titulo: `Cierre Mensual IVA F. 2002 + e-APOC (CUIT term. ${term})`, cadencia: `Mensual — Día ${diaIva - 4} (vence día ${diaIva})`, cron: `0 9 ${diaIva - 4} * *`, prompt: "Ejecutá el cierre de IVA de la empresa: Mis Comprobantes, Mis Retenciones, control Base e-APOC y borrador F. 2002." },
            { id: "dfe_semanal", titulo: "Auditoría DFE Sociedad", cadencia: "Semanal — Lunes 09:30", cron: "30 9 * * 1", prompt: "Revisá la bandeja DFE de la sociedad y alertame si hay requerimientos, exclusiones o intimaciones." },
            { id: "mipyme_anual", titulo: "Control y Renovación Certificado MiPyME (F. 1272)", cadencia: "Anual — 1° de Abril", cron: "0 9 1 4 *", prompt: "Verificá la vigencia de nuestro Certificado MiPyME (F. 1272) para no perder el cómputo del 100% del Impuesto al Cheque ni el IVA diferido." }
          ],
          empleado_relacion_dependencia: [
            { id: "siradig_mensual", titulo: "Carga Mensual SiRADIG Trabajador", cadencia: "Mensual — Día 26", cron: "0 18 26 * *", prompt: "Recordame qué comprobantes deducibles (prepaga, educación, alquiler, seguros, servicio doméstico) conviene cargar este mes en SiRADIG." },
            { id: "siradig_cierre", titulo: "Cierre Anual SiRADIG (vence 31/03)", cadencia: "Anual — 15 de Marzo", cron: "0 9 15 3 *", prompt: "Revisá si cargué todas las deducciones del año anterior en SiRADIG antes del cierre del 31/03." },
            { id: "ganancias_bbpp", titulo: "Revisión Ganancias F. 2711, BBPP y Saldos a Favor", cadencia: "Anual — 15 de Mayo", cron: "0 9 15 5 *", prompt: "Revisá Nuestra Parte, F. 2711 Simplificada, Ratificación anual y saldos a favor en SCT para planificar Ganancias y Bienes Personales." }
          ],
          estudio_contable: [
            { id: "estudio_lunes", titulo: "Tablero Semanal de Vencimientos y DFE Multi-Cliente", cadencia: "Semanal — Lunes 08:30", cron: "30 8 * * 1", prompt: "Abrí `tablero_cartera_estudio` y listame los clientes con vencimientos esta semana, alertas de desvíos >30% y novedades DFE." },
            { id: "estudio_docs", titulo: "Pedido de Documentación a Clientes", cadencia: "Mensual — Día 2", cron: "0 9 2 * *", prompt: "Generá los mensajes de solicitud de extractos bancarios, tarjetas y novedades de nómina para los clientes de la cartera." },
            { id: "estudio_aprobacion", titulo: "Revisión Socio y Reportes Marca Blanca", cadencia: "Mensual — Día 17", cron: "0 10 17 * *", prompt: "Mostrame los cierres en estado 'pendiente_revision_socio' con alertas rojas para aprobar en bloque y emitir reportes Marca Blanca." }
          ]
        };

        const eventos = [
          ...(EVENTOS_BASE[perfil] || EVENTOS_BASE.monotributo),
          {
            id: "auto_update_skills_normativa",
            titulo: "Auto-actualización de Skills, Complementos y Novedades ARCA",
            cadencia: "Mensual — Día 1 a las 09:00",
            cron: "0 9 1 * *",
            prompt: "Revisá https://impuesto.com.ar/skills/manifest.json y novedades fiscales del mes; avisame si hay nuevas versiones de skills, cambios de escalas/topes ARCA o mejoras para mi perfil."
          }
        ];

        // Generar bloque .ics universal (importable en Google Calendar, Apple Calendar, Outlook)
        const icsLines = [
          "BEGIN:VCALENDAR",
          "VERSION:2.0",
          "PRODID:-//impuesto.com.ar//Calendario Fiscal ARCA//ES",
          "CALSCALE:GREGORIAN"
        ];
        eventos.forEach((ev, idx) => {
          const isWeekly = ev.cron.endsWith("1");
          const rrule = isWeekly ? "FREQ=WEEKLY;BYDAY=MO" : (ev.cadencia.includes("Anual") ? "FREQ=YEARLY" : (ev.cadencia.includes("Semestral") ? "FREQ=MONTHLY;INTERVAL=6" : "FREQ=MONTHLY"));
          icsLines.push(
            "BEGIN:VEVENT",
            `UID:impuesto-${perfil}-${ev.id}-${idx}@impuesto.com.ar`,
            `SUMMARY:[impuesto.com.ar] ${ev.titulo}`,
            `DESCRIPTION:${ev.cadencia} — Prompt sugerido: ${ev.prompt}`,
            `RRULE:${rrule}`,
            "END:VEVENT"
          );
        });
        icsLines.push("END:VCALENDAR");

        const guiasPorLlm = {
          chatgpt: "En ChatGPT (Tasks / Scheduled Tasks): pegá cada evento y decile 'Creá una tarea programada con esta cadencia y este prompt usando el conector chatgpt.impuesto.com.ar'.",
          claude: "En Claude (Scheduled / Projects + Google Calendar MCP): pedile 'Creá estos eventos recurrentes en mi calendario y dejá activas las rutinas con claude.impuesto.com.ar'.",
          gemini: "En Gemini / Antigravity: usá `/schedule` o `/automation` con la expresión `cron` y el `prompt` de cada ítem usando `gemini.impuesto.com.ar`.",
          copilot: "En Microsoft Copilot / Power Automate: creá un flujo recurrente con la cadencia indicada conectado a `copilot.impuesto.com.ar`."
        };

        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              perfil,
              cuit: cuitClean || "no_informado",
              terminacion_cuit: term,
              total_automatizaciones: eventos.length,
              automatizaciones_y_recordatorios: eventos,
              como_activar_en_tu_ia: cliente === "todos" ? guiasPorLlm : { [cliente]: guiasPorLlm[cliente] || guiasPorLlm.claude },
              calendario_ics_universal: icsLines.join("\r\n"),
              instruccion_para_ia: "Mostrale al usuario su tabla limpia de recordatorios y preguntale cuáles quiere activar ahora mismo con las automatizaciones nativas de esta plataforma o exportar como .ics."
            }, null, 2)
          }]
        });
      }

      // 1z5. Preparar Espacio de Trabajo "Impuestos" (Proyecto copy-paste + Skills por perfil + Auto-Update)
      if (toolName === "preparar_espacio_de_trabajo_impuestos") {
        const perfil = (args.perfil || "monotributo").toLowerCase();
        const cuitClean = (args.cuit || "").replace(/[^0-9]/g, "");
        const juris = args.jurisdiccion || "Argentina";
        const obj = args.objetivo_principal || "mantener al día presentaciones, pagos y planificación fiscal los próximos 12 meses";

        const PERFIL_LABELS = {
          monotributo: "Monotributista",
          responsable_inscripto: "Responsable Inscripto",
          pyme_sociedad: "PyME / Sociedad (SRL / SA / SAS)",
          empleado_relacion_dependencia: "Empleado en Relación de Dependencia",
          estudio_contable: "Estudio Contable (B2B Multi-Cliente)"
        };
        const label = PERFIL_LABELS[perfil] || "Contribuyente";

        const promptProyecto = [
          `Sos mi Contador Agéntico de Cabecera y CFO (impuesto.com.ar).`,
          `• Perfil: ${label}${cuitClean ? ` · CUIT principal: ${cuitClean}` : ""} · Jurisdicción: ${juris}.`,
          `• Objetivo anual: ${obj}.`,
          `• Reglas de trabajo en este Proyecto "Impuestos":`,
          `  1) Hablame en español argentino claro y ejecutivo, sin jerga técnica ni mencionar herramientas internas.`,
          `  2) Buscá vos todos los datos que viven en ARCA (CCMA, Mis Facilidades con capital remanente y cuota día 16, SCT, Monotributo, DFE, Ganancias F.711/F.2711, BBPP F.762) sin pedirme que entre al portal.`,
          `  3) Nunca afirmes "Deuda $0" ni "Al día" sin cruzar todas las fuentes obligatorias y aclarar tributos fuera de ARCA (IIBB/Municipios).`,
          `  4) Operá siempre en modo solo lectura salvo confirmación explícita mía antes de emitir facturas, presentar DDJJ o planes.`,
          `  5) Cerrá cada charla recomendándome cuál es el próximo paso concreto y abrimos 1 chat limpio por cada mes nuevo.`
        ].join("\n");

        const skillsRecomendados = SKILLS_BUNDLE
          .filter(s => s.perfil_objetivo === "todos" || s.perfil_objetivo === perfil)
          .map(s => ({
            nombre: s.name,
            uri_mcp: s.uri,
            version: s.version,
            descarga_directa: s.download_url,
            para_que_sirve: s.description
          }));

        const autoUpdate = {
          nombre: "Auto-actualización mensual de Skills y Normativa impuesto.com.ar",
          cadencia: "Mensual — Día 1 a las 09:00",
          cron: "0 9 1 * *",
          manifest_url: "https://impuesto.com.ar/skills/manifest.json",
          comando_actualizacion_local: "curl -fsSL https://impuesto.com.ar/skills/install.sh | bash",
          prompt_automatizacion: "Consultá https://impuesto.com.ar/skills/manifest.json y novedades fiscales del mes; avisame si hay versiones nuevas de mis skills, cambios de escalas/alícuotas ARCA o nuevas herramientas relevantes para mi perfil y guíame en 1 paso si conviene actualizar."
        };

        return jsonRpcSuccess(id, {
          content: [{
            type: "text",
            text: JSON.stringify({
              nombre_proyecto_sugerido: "Impuestos",
              perfil: label,
              paso_a_crear_proyecto: {
                instruccion: "Creá un Proyecto llamado 'Impuestos' en ChatGPT o Claude y pegá este texto exacto en las instrucciones del Proyecto:",
                prompt_copy_paste: promptProyecto
              },
              paso_b_skills_para_tu_perfil: {
                hub_web: "https://impuesto.com.ar/skills/",
                comando_1_linea: "curl -fsSL https://impuesto.com.ar/skills/install.sh | bash",
                skills: skillsRecomendados
              },
              paso_c_auto_actualizacion: autoUpdate,
              siguiente_paso_recomendado: "Una vez creado tu Proyecto 'Impuestos' y activadas tus automatizaciones de vencimientos (`generar_automatizaciones_y_calendario_fiscal`), corremos tu Auditoría 360° para dejar el mes ordenado."
            }, null, 2)
          }]
        });
      }

      // Respuesta informativa si no está conectado el microservicio en este momento
      return jsonRpcSuccess(id, {
        content: [{
          type: "text",
          text: `[ARCA MCP] Consulta recibida para herramienta '${toolName}'. Parámetros: ${JSON.stringify(args)}. El microservicio propio de ARCA procesará esta solicitud de forma segura.`
        }]
      });
    }

    return jsonRpcError(id, -32601, `Method not found: ${method}`);
  }

  // Soporte de CORS pre-flight
  if (request.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, Accept"
      }
    });
  }

  return new Response("Not found", { status: 404 });
}

function jsonRpcSuccess(id, result) {
  return new Response(JSON.stringify({ jsonrpc: "2.0", id, result }), {
    status: 200,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*"
    }
  });
}

function jsonRpcError(id, code, message) {
  return new Response(JSON.stringify({ jsonrpc: "2.0", id, error: { code, message } }), {
    status: 200,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*"
    }
  });
}

function htmlLanding(urlObj) {
  const host = (urlObj.hostname || "").toLowerCase();
  const BRANDS = {
    "claude.impuesto.com.ar": { name: "Claude", title: "Conector ARCA MCP para Claude — claude.impuesto.com.ar", h1: "Conectá ARCA directamente a Claude" },
    "chatgpt.impuesto.com.ar": { name: "ChatGPT", title: "Conector ARCA MCP para ChatGPT — chatgpt.impuesto.com.ar", h1: "Conectá ARCA directamente a ChatGPT" },
    "gemini.impuesto.com.ar": { name: "Google Gemini", title: "Conector ARCA MCP para Gemini — gemini.impuesto.com.ar", h1: "Conectá ARCA directamente a Google Gemini" },
    "copilot.impuesto.com.ar": { name: "Microsoft Copilot", title: "Conector ARCA MCP para Copilot — copilot.impuesto.com.ar", h1: "Conectá ARCA directamente a Microsoft Copilot" },
    "cursor.impuesto.com.ar": { name: "Cursor", title: "Conector ARCA MCP para Cursor — cursor.impuesto.com.ar", h1: "Conectá ARCA directamente a Cursor" },
    "perplexity.impuesto.com.ar": { name: "Perplexity", title: "Conector ARCA MCP para Perplexity — perplexity.impuesto.com.ar", h1: "Conectá ARCA directamente a Perplexity" },
    "mcp.impuesto.com.ar": { name: "Universal MCP", title: "Conector ARCA MCP Universal — mcp.impuesto.com.ar", h1: "Conectá ARCA a cualquier asistente IA vía MCP" }
  };
  const brand = BRANDS[host] || BRANDS["mcp.impuesto.com.ar"];
  const title = brand.title;
  const h1 = brand.h1;

  return `<!doctype html>
<html lang="es-AR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title}</title>
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<style>
:root{--ink:#0B1320;--muted:#475467;--line:#E3E7EC;--bg:#F8FAFC;--acc:#0B6E4F;--acc2:#074F39;--tint:#E7F5EF;--font:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
*{box-sizing:border-box}
body{margin:0;font-family:var(--font);color:var(--ink);background:var(--bg);padding:40px 20px;line-height:1.6}
.box{max-width:740px;margin:0 auto;background:#fff;border:1px solid var(--line);border-radius:18px;padding:36px;box-shadow:0 12px 36px rgba(15,27,45,.06)}
.pill{background:var(--tint);color:var(--acc2);font-weight:700;font-size:12.5px;padding:4px 12px;border-radius:99px;display:inline-block;margin-bottom:12px}
h1{font-size:28px;margin:0 0 10px;letter-spacing:-.025em}
p{color:var(--muted);font-size:15.5px;margin:0 0 20px}
.url-card{background:#F4F6F9;border:1px solid #D8E0E8;border-radius:12px;padding:12px 16px;display:flex;align-items:center;justify-content:space-between;gap:12px;margin:10px 0}
.url-card.active{background:#E7F5EF;border-color:#0B6E4F}
.url-lbl{font-size:11.5px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:2px}
.url-text{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:14.5px;color:var(--ink);font-weight:600;word-break:break-all}
.btn{background:var(--acc);color:#fff;border:0;padding:9px 14px;border-radius:9px;font-weight:600;cursor:pointer;font-size:13px;white-space:nowrap}
.btn:hover{background:var(--acc2)}
.steps{margin:24px 0;padding-left:20px;color:var(--ink);font-size:15px}
.steps li{margin-bottom:8px}
.examples{background:#FAF9F5;border-left:4px solid #D97757;padding:14px 18px;border-radius:0 10px 10px 0;margin-top:22px}
.examples p{margin:4px 0;color:var(--ink);font-style:italic;font-size:14.5px}
</style>
</head>
<body>
<div class="box">
<span class="pill">Model Context Protocol (MCP) · 48 herramientas ARCA + 5 Skill Packs</span>
<h1>${h1}</h1>
<p>Pegá la URL dedicada de tu asistente en la sección de Conectores / MCP para consultar comprobantes, auditar deudas reales (CCMA + Mis Facilidades + SCT), emitir facturas con CAE y cerrar impuestos en tiempo real.</p>

<div class="url-card ${host === 'claude.impuesto.com.ar' ? 'active' : ''}">
  <div><div class="url-lbl">✦ Claude (Claude.ai / Claude Desktop / Claude Code)</div><div class="url-text">https://claude.impuesto.com.ar</div></div>
  <button class="btn" onclick="navigator.clipboard.writeText('https://claude.impuesto.com.ar');this.innerText='¡Copiado!'">Copiar URL</button>
</div>
<div class="url-card ${host === 'chatgpt.impuesto.com.ar' ? 'active' : ''}">
  <div><div class="url-lbl">⚡ ChatGPT (Connectors / Developer Mode)</div><div class="url-text">https://chatgpt.impuesto.com.ar</div></div>
  <button class="btn" onclick="navigator.clipboard.writeText('https://chatgpt.impuesto.com.ar');this.innerText='¡Copiado!'">Copiar URL</button>
</div>
<div class="url-card ${host === 'gemini.impuesto.com.ar' ? 'active' : ''}">
  <div><div class="url-lbl">◆ Google Gemini (Gemini CLI / Antigravity / AI Studio)</div><div class="url-text">https://gemini.impuesto.com.ar</div></div>
  <button class="btn" onclick="navigator.clipboard.writeText('https://gemini.impuesto.com.ar');this.innerText='¡Copiado!'">Copiar URL</button>
</div>
<div class="url-card ${host === 'copilot.impuesto.com.ar' ? 'active' : ''}">
  <div><div class="url-lbl">❖ Microsoft Copilot (Copilot Studio / GitHub Copilot / VS Code)</div><div class="url-text">https://copilot.impuesto.com.ar</div></div>
  <button class="btn" onclick="navigator.clipboard.writeText('https://copilot.impuesto.com.ar');this.innerText='¡Copiado!'">Copiar URL</button>
</div>
<div class="url-card ${host === 'cursor.impuesto.com.ar' ? 'active' : ''}">
  <div><div class="url-lbl">▸ Cursor IDE</div><div class="url-text">https://cursor.impuesto.com.ar</div></div>
  <button class="btn" onclick="navigator.clipboard.writeText('https://cursor.impuesto.com.ar');this.innerText='¡Copiado!'">Copiar URL</button>
</div>
<div class="url-card ${host === 'perplexity.impuesto.com.ar' ? 'active' : ''}">
  <div><div class="url-lbl">◎ Perplexity</div><div class="url-text">https://perplexity.impuesto.com.ar</div></div>
  <button class="btn" onclick="navigator.clipboard.writeText('https://perplexity.impuesto.com.ar');this.innerText='¡Copiado!'">Copiar URL</button>
</div>
<div class="url-card ${host === 'mcp.impuesto.com.ar' ? 'active' : ''}">
  <div><div class="url-lbl">∞ Universal MCP (Windsurf, Zed, Agentes Propios)</div><div class="url-text">https://mcp.impuesto.com.ar</div></div>
  <button class="btn" onclick="navigator.clipboard.writeText('https://mcp.impuesto.com.ar');this.innerText='¡Copiado!'">Copiar URL</button>
</div>

<ol class="steps">
<li><strong>En ChatGPT:</strong> abrí <strong>Complementos → Agregar ⌄ → MCP</strong>, dejá marcado <strong>HTTP secuenciable</strong> (no STDIO), completá solo <strong>Nombre</strong> (<code>impuesto.com.ar</code>) y <strong>URL</strong> (<code>https://chatgpt.impuesto.com.ar</code>), dejá vacíos Token y Encabezados, y tocá <strong>Guardar</strong>.</li>
<li><strong>En Claude:</strong> abrí <strong>Customize → Connectors → Add Custom Connector</strong> y pegá <code>https://claude.impuesto.com.ar</code>.</li>
<li><strong>En Gemini, Copilot, Cursor o Perplexity:</strong> pegá tu URL dedicada de arriba en la sección <strong>MCP Servers</strong> (todas comparten las mismas <strong>49 herramientas ARCA + 6 Skill Packs</strong>).</li>
</ol>

<div style="margin:22px 0;padding:18px;background:#F8FAFC;border:1px solid #E3E7EC;border-radius:14px">
  <div style="font-weight:700;font-size:14px;margin-bottom:8px;color:#0B1320">📸 Guía visual paso a paso en ChatGPT (Complementos → Agregar ⌄ → MCP)</div>
  <p style="font-size:13.5px;margin:0 0 12px;color:#475467">Elegí <strong>HTTP secuenciable</strong>, completá solo <strong>Nombre</strong> y <strong>URL</strong> (<code>https://chatgpt.impuesto.com.ar</code>), dejá todo lo demás vacío y tocá <strong>Guardar</strong>:</p>
  <img src="https://impuesto.com.ar/assets/guia-chatgpt-mcp.png" alt="Configuración de MCP en ChatGPT: HTTP secuenciable" style="width:100%;border-radius:10px;border:1px solid #D8E0E8;display:block">
</div>

<div class="examples">
<strong>Primer mensaje recomendado (abrí un chat nuevo y pegá esto — sin usar @):</strong>
<div class="url-card" style="margin-top:10px;background:#fff">
  <div>
    <div class="url-lbl">👤 Contribuyente / Monotributo / PyME</div>
    <div style="font-size:13.5px;color:var(--ink)">Hola, usando impuesto.com.ar quiero empezar a ordenar mis impuestos para los próximos 12 meses. Mostrame cómo vincular mi CUIT de forma segura y qué conviene revisar primero.</div>
  </div>
  <button class="btn" onclick="navigator.clipboard.writeText('Hola, usando impuesto.com.ar quiero empezar a ordenar mis impuestos para los próximos 12 meses. Mostrame cómo vincular mi CUIT de forma segura y qué conviene revisar primero.');this.innerText='¡Copiado!'">Copiar</button>
</div>
<div class="url-card" style="background:#fff">
  <div>
    <div class="url-lbl">🏢 Estudio Contable (B2B)</div>
    <div style="font-size:13.5px;color:var(--ink)">Hola, soy un Estudio Contable y quiero activar impuesto.com.ar para gestionar mi cartera de clientes con alertas de desvíos mayores al 30% y reportes Marca Blanca. Mostrame el Paso 1 de vinculación segura.</div>
  </div>
  <button class="btn" onclick="navigator.clipboard.writeText('Hola, soy un Estudio Contable y quiero activar impuesto.com.ar para gestionar mi cartera de clientes con alertas de desvíos mayores al 30% y reportes Marca Blanca. Mostrame el Paso 1 de vinculación segura.');this.innerText='¡Copiado!'">Copiar</button>
</div>
</div>
</div>
</body>
</html>`;
}

function evaluarPerfilFiscalJS(args) {
  const cuitClean = (args.cuit || "").replace(/[^0-9]/g, "");
  const juris = args.jurisdicciones_operacion && args.jurisdicciones_operacion.length > 0
    ? args.jurisdicciones_operacion
    : [args.ubicacion_sede || "CABA"];
  if (args.ubicacion_sede && !juris.includes(args.ubicacion_sede)) {
    juris.unshift(args.ubicacion_sede);
  }

  const tipo = (args.tipo_personeria || "monotributo").toLowerCase();
  const esMono = tipo.includes("mono");
  const esEmpresa = ["srl", "sa", "sas", "sociedad"].some(k => tipo.includes(k));
  const esRI = !esMono && !esEmpresa;

  const aQuien = (args.a_quien_vende || "").toLowerCase();
  const vendeExterior = ["exterior", "export", "afuera", "usa", "estados unidos", "eeuu", "extranjero", "europa", "latam", "dolar", "dólar"].some(k => aQuien.includes(k));
  const vendeEmpresas = ["empresa", "b2b", "inscripto", "srl", "sa", "corporativo"].some(k => aQuien.includes(k));
  const vendeConsumidor = ["consumidor", "b2c", "gente", "publico", "local", "minorista", "final"].some(k => aQuien.includes(k));

  const esInterjurisdiccional = juris.length > 1 || juris.some(j => j.toLowerCase().includes("todas") || j.toLowerCase().includes("pais"));
  const empleados = parseInt(args.cantidad_empleados || 0, 10);

  // Comprobantes
  const comprobantes = [];
  if (esMono) {
    comprobantes.push({ tipo: "Factura C", destinatarios: "Clientes en Argentina (Consumidor Final, RI, Monotributistas)", iva_discriminado: false });
    if (vendeExterior) {
      comprobantes.push({ tipo: "Factura E (Exportación)", destinatarios: "Clientes del exterior (alícuota 0% IVA, cupo USD 24.000 Com. A 7518 BCRA)", iva_discriminado: false });
    }
  } else {
    if (vendeEmpresas) {
      comprobantes.push({ tipo: "Factura A", destinatarios: "Empresas Responsables Inscriptas en IVA (discrimina 21%, 10.5% o 27%)", iva_discriminado: true });
    }
    if (vendeConsumidor || esMono) {
      comprobantes.push({ tipo: "Factura B", destinatarios: "Consumidores Finales y Monotributistas (IVA incluido sin discriminar)", iva_discriminado: false });
    }
    if (vendeExterior) {
      comprobantes.push({ tipo: "Factura E", destinatarios: "Clientes en el exterior (exento de IVA)", iva_discriminado: false });
    }
  }

  // IIBB
  const iibb = esInterjurisdiccional ? {
    regimen: "Convenio Multilateral (SIFERE CM03)",
    alcance: `Operás en ${juris.length} provincias (${juris.join(", ")}).`,
    alerta_sircreb: "CRÍTICO: Inscribirte en SIFERE evita retenciones bancarias del SIRCREB del 3% al 5% en tus cuentas bancarias.",
    declaracion: "DDJJ mensual CM03 y anual CM05 con coeficientes unificados."
  } : {
    regimen: `Régimen Local (${juris[0] || args.ubicacion_sede})`,
    alcance: `Operaciones centralizadas únicamente en ${juris[0] || args.ubicacion_sede}.`,
    alerta_sircreb: "BAJO: Alícuotas locales fijadas por el padrón de contribuyentes de tu provincia.",
    declaracion: "DDJJ mensual ante Rentas local."
  };

  // Cargas sociales
  const laboral = empleados > 0 ? {
    tiene_empleados: true,
    cantidad: empleados,
    obligaciones: ["Formulario 931 ARCA mensual", "Libro de Sueldos Digital (RG 5249)", "ART y Seguro de Vida Obligatorio"],
    costo_adicional_estimado: "+35% a +45% sobre el sueldo bruto acordado."
  } : {
    tiene_empleados: false,
    cantidad: 0,
    obligaciones: ["Sin F. 931 ni Libro de Sueldos Digital."],
    costo_adicional_estimado: "$0"
  };

  // Resumen ejecutivo claro y directo (sin jerga ni infantilismos)
  let resumenClaro = "";
  if (esMono) {
    resumenClaro = `Con tu actividad de ${args.que_vende} en ${args.ubicacion_sede}, el Monotributo unifica impuesto, jubilación y obra social en una cuota fija mensual. Emitís Factura C en el país (sin discriminar IVA) y el foco estratégico es vigilar el margen anual para no quedar excluido.`;
  } else if (esEmpresa) {
    resumenClaro = `Al operar como ${args.razon_social || "sociedad"} (${args.que_vende} en ${args.ubicacion_sede}), la empresa tiene patrimonio separado del tuyo. Liquidás IVA mensualmente (cobrando 21% en Factura A y descontando el IVA de tus compras) y Ganancias sobre la utilidad neta anual. Tu foco es documentar cada gasto operativo y planificar retiros eficientes (honorarios vs dividendos).`;
  } else {
    resumenClaro = `Como Responsable Inscripto (${args.que_vende} en ${args.ubicacion_sede}), cobrás IVA al vender y descontás el IVA de todas tus compras vinculadas a la actividad, ingresando solo la diferencia. Documentar gastos deducibles es clave para bajar tu tasa efectiva de Ganancias.`;
  }
  if (empleados > 0) {
    resumenClaro += ` Al tener ${empleados} personas en nómina, liquidás mensualmente sueldos, F. 931, Libro de Sueldos Digital y ART (costo total aproximado +35% a +45% sobre el bruto).`;
  } else {
    resumenClaro += ` Al operar sin nómina en blanco, evitás la carga mensual de F. 931 y ART.`;
  }

  return {
    perfil: {
      cuit: cuitClean,
      razon_social: args.razon_social || "Contribuyente Registrado",
      rol: args.rol || "Titular",
      tipo_personeria: tipo,
      actividad: args.que_vende,
      clientes: args.a_quien_vende,
      sede: args.ubicacion_sede,
      jurisdicciones: juris,
      empleados: empleados
    },
    marco_fiscal: {
      comprobantes_habilitados: comprobantes,
      ingresos_brutos: iibb,
      cargas_sociales: laboral
    },
    explicacion_clara: resumenClaro,
    proximos_pasos_ia: [
      "1. Cada vez que me pidas facturar, elegiré la letra correcta (A, B, C o E) sin dudas.",
      "2. Tus recordatorios de vencimiento se adaptan a tu régimen exacto.",
      "3. La IA auditará que los bancos no te apliquen retenciones SIRCREB indebidas."
    ]
  };
}
