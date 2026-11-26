---
name: impuesto-monotributo-y-recategorizacion
description: Gestiona Monotributo en ARCA: control de tope de categoría, prevención de exclusión, deuda CCMA, débito automático, facturación Factura C/E y calendario de vencimientos.
version: 2.0.0
perfil_objetivo: monotributo
---

# Monotributo y Recategorización Inteligente (impuesto.com.ar)

## Objetivo
Mantener al monotributista 100% al día, evitar la baja automática por mora (10 cuotas consecutivas impagas, Art. 36 Dto. 1/2010) y anticipar con 60 días cualquier salto de categoría o riesgo de exclusión hacia Responsable Inscripto / S.R.L.

## Checklist Mensual Obligatorio
1. **Margen de Categoría:** Consultar en Portal Monotributo la facturación electrónica acumulada de los últimos 12 meses vs. tope de la categoría actual (servicios vs. venta de cosas muebles) y calcular el margen disponible en pesos y porcentaje.
2. **Deuda Real (Double-Check):** Cruzar **CCMA** (Imp. 020 + 021 + 024 + intereses resarcitorios) + **Mis Facilidades** (planes RG 5321 vigentes). Nunca confiar solo en SCT.
3. **Monotributo Unificado / IIBB:** Verificar si la jurisdicción (AGIP CABA / ARBA PBA / Córdoba / Mendoza) está unificada en la credencial o excluida por trámite.
4. **Domicilio Fiscal Electrónico (DFE):** Verificar notificaciones nuevas para evitar recategorizaciones de oficio o exclusiones por acreditaciones bancarias.
5. **Débito Automático:** Recomendar adhesión a débito automático (otorga reintegro de 1 cuota anual del componente impositivo por cumplimiento).

## Reglas de Facturación y Exportación
- Ventas en Argentina: **Factura C** (no discrimina IVA).
- Exportación de servicios al exterior: **Factura E** (alícuota 0% IVA, cupo anual sin pesificación Com. A 7518 BCRA).
- Antes de emitir cualquier comprobante (`emitir_factura_wsfe`), mostrar borrador y exigir `confirmado=true`.

## Automatizaciones al Instalar
Al activar este skill, llamar a `generar_automatizaciones_y_calendario_fiscal(perfil="monotributo", cuit=...)` y ofrecer crear los recordatorios nativos del asistente (pago día 18/20, control de tope día 25, recategorización Enero y Julio, revisión DFE semanal).
