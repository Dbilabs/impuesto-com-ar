---
name: impuesto-estudio-contable-b2b
description: Opera el Modo Estudio Contable B2B: gestión de cartera multi-cliente, tablero por terminación de CUIT, detección automática de desvíos >30%, flujo Junior→Socio y reportes Marca Blanca.
version: 2.0.0
perfil_objetivo: estudio_contable
---

# Modo Estudio Contable B2B (impuesto.com.ar)

## Higiene de Chats y Memoria Multi-Cliente
- La memoria fiscal de cada cliente vive en la base de datos del conector (no en chats eternos).
- Recomendación operativa para el estudio: abrir **1 chat limpio por cierre mensual o por cliente crítico**; el conector recupera automáticamente el perfil, historial y alertas del estudio sin perder contexto.

## Flujo Operativo del Estudio
1. **Alta de Estudio y Cartera:** `configurar_estudio_contable` (nombre, CUIT, socio responsable, pie Marca Blanca) + `importar_cartera_clientes` en lote.
2. **Tablero de Control:** `tablero_cartera_estudio(estudio_id, periodo)` ordena vencimientos por terminación de CUIT (`0-9`), carga por analista y semáforo de estado.
3. **Control de Calidad Junior → Socio (`registrar_cierre_y_detectar_anomalias`):**
   - Todo borrador queda en estado `pendiente_revision_socio` (NUNCA presenta directo en ARCA).
   - Cualquier desvío **>30%** respecto al mes anterior dispara **Alerta Roja** automática para auditoría del Socio.
4. **Aprobación en Bloque y Comunicación Marca Blanca:**
   - El Socio aprueba con `aprobar_cierres_socio`.
   - Se genera el mensaje listo para WhatsApp o email con `generar_reporte_marca_blanca_cliente` (100% con el nombre y firma del estudio, sin mencionar terceros).

## Automatizaciones al Instalar
Llamar a `generar_automatizaciones_y_calendario_fiscal(perfil="estudio_contable", cuit=...)` para crear la cadencia semanal del estudio: lunes (revisión DFE + vencimientos de la semana por CUIT), días 1–5 (solicitud de documentación a clientes), días 8–12 (cierre F. 931), días 15–22 (cierre IVA/IIBB y alertas >30%), día 25 (reportes Marca Blanca).
