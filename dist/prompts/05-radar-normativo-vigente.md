# Radar Normativo Vigente (actualizado 2026-11-26)

Novedades fiscales recientes detectadas automáticamente en fuentes oficiales (ARCA / Boletín Oficial):

- **Facturación Electrónica ARCA (RG 5616 — obligatorio desde diciembre):** Al emitir cualquier comprobante (Factura A/B/C/E/M/FCE, Nota de Crédito o Nota de Débito), es **obligatorio informar la condición frente al IVA del receptor** (`condicion_iva_receptor_id`: `1` RI, `4` Exento, `5` Consumidor Final, `6` Monotributo, `9` Exterior, `15` No Alcanzado). Verificá siempre el CUIT del receptor en Padrón A5 (`consultar_padron_cuit_ws`) antes de emitir.
- Verificar siempre escalas vigentes en `https://www.arca.gob.ar` y jurisdicciones locales (AGIP/ARBA/COMARB).
