# Radar Normativo Vigente (actualizado 2026-11-26)

Novedades fiscales y de facturación electrónica 2026–2027 vigentes en ARCA y jurisdicciones locales:

- **1/7/2026 — Consumidor Final (RG ARCA 5866/2026 y RG 5700/2025):** Solo es obligatorio identificar al Consumidor Final (DNI/CUIL/CDI) en ventas de **\$10.000.000 o más** (sin distinguir medio de pago), salvo que el cliente pida CUIT para deducir en Ganancias.
- **1/11/2026 — Monotributo Social (RG ARCA 5893/2026):** Factura electrónica obligatoria para Monotributo Social y efectores de economía social (talonario impreso solo para contingencias).
- **1/12/2026 — Condición frente al IVA del receptor obligatoria (RG ARCA 5616/2024):** ARCA **rechaza** comprobantes emitidos vía Web Service (`WSFEv1`: Facturas A/B/C/E/M/FCE, Notas de Crédito y Notas de Débito) que no informen `condicion_iva_receptor_id` (`1` RI, `4` Exento, `5` Consumidor Final, `6` Monotributo, `9` Exterior, `15` No Alcanzado). Verificar siempre el CUIT del cliente en Padrón A5 (`consultar_padron_cuit_ws`) antes de emitir.
- **1/1/2027 — Discriminación IIBB CABA en Consumidor Final (Res. AGIP 169/2026, prorrogada por Res. 339/2026):** Obligatorio para contribuyentes de IIBB CABA (excepto Monotributo) mostrar la leyenda `ALÍCUOTA ISIB CABA` con el porcentaje en comprobantes a Consumidor Final.
- **1/3/2027 — No alcanzados por IVA (RG ARCA 5893/2026):** Factura electrónica obligatoria para sujetos no alcanzados por IVA (talonario solo contingencias).
- Verificar siempre escalas vigentes en `https://www.arca.gob.ar` y jurisdicciones locales (AGIP/ARBA/COMARB).
