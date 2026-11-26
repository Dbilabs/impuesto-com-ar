---
name: impuesto-auditoria-deuda-real
description: Audita el estado de cuenta y deuda real en ARCA sin falsos negativos cruzando CCMA, Mis Facilidades (capital remanente y cuota día 16), todas las CUITs representadas, SCT y Portal Monotributo, con Sello de Verificación.
version: 2.2.0
perfil_objetivo: todos
---

# Auditoría de Deuda Real y Planes en ARCA (impuesto.com.ar)

## Regla de Oro (Prohibición de Falsos Negativos)
NUNCA afirmes "Deuda $0", "Sin deuda" ni "Al día" mirando una sola pantalla de ARCA.
En Argentina, SCT (`Estado de Cumplimiento`) solo abarca 1 año de impuestos generales DGI, NO muestra Monotributo ni Autónomos (viven en CCMA) y oculta millones consolidados en planes de Mis Facilidades (que ponen el saldo de CCMA/SCT en `$0,00` bajo la leyenda *"Crédito por PFP Mis Facilidades"*).

## Reglas Obligatorias de Reporte (Sin Omisiones)
1. **Planes Vigentes en Mis Facilidades (OBLIGATORIO):** Si el contribuyente tiene planes vigentes, NUNCA te limites a decir "tenés N planes vigentes". Debés informar SIEMPRE:
   - Número de plan, régimen, cuotas pagas / totales, **cuotas impagas o riesgo de caducidad**, **capital remanente total** y **débito automático mensual total del día 16**.
   - Sumar **CCMA vencido hoy + Capital remanente de planes vigentes = Pasivo Total Real en ARCA**.
2. **Cruce de TODAS las CUITs Representadas (OBLIGATORIO):** Al leer el `<select>` de SCT / Mis Facilidades / Administrador de Relaciones, detectar automáticamente todas las sociedades o entidades vinculadas (ej. SRL, SA, Cooperativas) y mencionarlas por nombre y CUIT antes de preguntar al usuario si tiene otros cargos.
3. **Sello de Verificación + Fuera de ARCA (OBLIGATORIO):** Cerrar SIEMPRE con el Sello de Verificación (`validar_cobertura_auditoria_arca`) indicando qué fuentes se revisaron y advirtiendo expresamente que **Ingresos Brutos (AGIP/ARBA/SIFERE), Tasas Municipales y Juicios** están fuera de ARCA.
4. **Respaldo Humano (Human-in-the-Loop):** Ante bajas retroactivas, cesación de gerencia en IGJ, exclusiones o intimaciones, ofrecer siempre validación con **Contador Público Matriculado** (`solicitar_revision_contador_humano`).

## Protocolo Pre-Flight Obligatorio (7 pasos)
1. Identidad activa en `<select>` por texto exacto (nunca índice 0).
2. Disparar botones de cálculo (`Cálculo de Deuda`, `Filtrar`, `Siguiente`).
3. Ir siempre a historial (`#/declaraciones.anteriores`, `Seguimiento de Presentación`).
4. Expandir filtros (`48 períodos`) y recorrer todas las páginas (`Página 1 de N`).
5. Leer texto visible + `<input>.value`, `<iframe>` y cerrar modales/tooltips.
6. Cruzar módulos hermanos (CCMA ↔ Mis Facilidades ↔ SCT ↔ Monotributo).
7. Habilitar popups y capturar pestañas nuevas sin exponer ventanas confusas al usuario.

## UX de Seguridad y Continuidad
- Ejecutar las consultas en segundo plano (sin pedirle al usuario que escriba su Clave Fiscal en ventanas emergentes de Chrome que generen desconfianza) e informar claramente en el chat cada paso en modo solo lectura.
- Al finalizar el diagnóstico, ofrecer inmediatamente guardar el perfil (`configurar_perfil_contribuyente`) y activar las automatizaciones mensuales (`generar_automatizaciones_y_calendario_fiscal`) para evitar que se vuelva a acumular deuda.
