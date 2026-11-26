---
name: impuesto-cierre-mensual-pyme
description: Orquesta el cierre impositivo mensual de Responsables Inscriptos y PyMEs (SRL/SA/SAS): IVA, F. 931, proveedores e-APOC, retenciones, Certificado MiPyME F. 1272 y análisis CFO.
version: 2.0.0
perfil_objetivo: pyme_sociedad
---

# Cierre Mensual PyME y Responsable Inscripto (impuesto.com.ar)

## Flujo de Cierre Mensual (Paso a Paso)
1. **Recuperar Perfil Persistente:** Llamar a `obtener_perfil_contribuyente(cuit)` para no repetir preguntas mes a mes (encuadre IVA, jurisdicciones Local vs. Convenio Multilateral SIFERE, nómina F. 931).
2. **Cruzar Fuentes ARCA (Double-Check):**
   - `Mis Comprobantes` (Emitidos + Recibidos) → separar débito fiscal, crédito fiscal y notas de crédito.
   - `Mis Retenciones` (SIRE / SICORE) → computar todas las retenciones/percepciones nacionales.
   - `Base e-APOC` (`verificar_proveedor_apocrifo_apoc`) → auditar proveedores nuevos o montos significativos ANTES de computar crédito fiscal de IVA o gasto en Ganancias.
   - `SCT` (Imp. 30 IVA, Imp. 301/302/351/352 Seguridad Social, Imp. 10 Ganancias) + `Mis Facilidades` (planes vigentes y vencimientos día 16).
3. **Pedir Documentación Fuera de ARCA:** Llamar a `solicitar_documentos_complementarios` (extractos bancarios para SIRCREB/Impuesto al Cheque, tarjetas corporativas, nómina/novedades de sueldos, boletas sindicales y ART).
4. **Optimización PyME Obligatoria:**
   - Verificar vigencia del **Certificado MiPyME (F. 1272)** (`consultar_y_renovar_certificado_mipyme`) para activar: 100% de Impuesto a los Débitos y Créditos a cuenta de Ganancias, diferimiento de IVA a 90 días y avales SGR.
   - Distinguir **Saldo Técnico IVA** (no compensable) vs. **Saldo de Libre Disponibilidad** (compensable en SCT).
   - Evaluar retiros de socios: Honorarios a directores/socios gerentes (Art. 91 inc. i LIG) vs. Dividendos (7%).

## Automatizaciones al Instalar
Llamar a `generar_automatizaciones_y_calendario_fiscal(perfil="pyme_sociedad", cuit=...)` para agendar vencimientos exactos por terminación de CUIT: F. 931 (días 9–11), débito planes (día 16), IVA F. 2002 (días 18–22), IIBB/CM03, DFE semanal y renovación MiPyME.
