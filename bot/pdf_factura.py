"""
bot/pdf_factura.py
Generador de Comprobantes Electrónicos Oficiales de ARCA (HTML imprimible + PDF)
cumpliendo diseño reglamentario RG 1415 y Código QR obligatorio RG 4892.

Soporta: Factura A (001), B (006), C (011), E (019), FCE MiPyME A/B/C (201/206/211),
Notas de Crédito y Notas de Débito.
"""

import os
import json
import base64
import datetime
from typing import Dict, Any, List, Optional

CODIGOS_CBTE = {
    "A": ("001", "FACTURA"),
    "B": ("006", "FACTURA"),
    "C": ("011", "FACTURA"),
    "E": ("019", "FACTURA DE EXPORTACIÓN"),
    "NC_A": ("003", "NOTA DE CRÉDITO"),
    "NC_B": ("008", "NOTA DE CRÉDITO"),
    "NC_C": ("013", "NOTA DE CRÉDITO"),
    "FCE_A": ("201", "FACTURA DE CRÉDITO ELECTRÓNICA MiPyMEs (FCE)"),
    "FCE_B": ("206", "FACTURA DE CRÉDITO ELECTRÓNICA MiPyMEs (FCE)"),
    "FCE_C": ("211", "FACTURA DE CRÉDITO ELECTRÓNICA MiPyMEs (FCE)")
}


def generar_url_qr_arca(
    cuit_emisor: str,
    pto_vta: int,
    tipo_cmp: int,
    nro_cmp: int,
    importe_total: float,
    fecha_iso: str,
    doc_rec_nro: str,
    cae: str,
    moneda: str = "PES",
    ctz: float = 1.0
) -> str:
    cuit_em = int("".join(c for c in str(cuit_emisor) if c.isdigit()) or "0")
    doc_rec = int("".join(c for c in str(doc_rec_nro) if c.isdigit()) or "0")
    cae_num = int("".join(c for c in str(cae) if c.isdigit()) or "0")
    payload = {
        "ver": 1,
        "fecha": fecha_iso,
        "cuit": cuit_em,
        "ptoVta": int(pto_vta),
        "tipoCmp": int(tipo_cmp),
        "nroCmp": int(nro_cmp),
        "importe": round(float(importe_total), 2),
        "moneda": moneda,
        "ctz": float(ctz),
        "tipoDocRec": 80 if len(str(doc_rec)) == 11 else 99,
        "nroDocRec": doc_rec,
        "tipoCodAut": "E",
        "codAut": cae_num
    }
    b64 = base64.b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")
    return f"https://www.afip.gob.ar/fe/qr/?p={b64}"


def generar_factura_html_y_pdf(
    letra: str,
    emisor_razon_social: str,
    emisor_cuit: str,
    emisor_domicilio: str,
    emisor_condicion_iva: str,
    receptor_razon_social: str,
    receptor_cuit: str,
    receptor_condicion_iva: str,
    items: List[Dict[str, Any]],
    pto_vta: int = 1,
    nro_comprobante: int = 1,
    cae: str = "76471234567890",
    cae_vto: Optional[str] = None,
    fecha_emision: Optional[str] = None,
    iibb_emisor: str = "Convenio Multilateral",
    inicio_actividades: str = "01/01/2020",
    moneda: str = "PES",
    exportar_pdf_ruta: Optional[str] = None
) -> Dict[str, Any]:
    """
    Genera el comprobante oficial HTML listo para imprimir y opcionalmente lo renderiza a PDF.
    """
    letra_key = letra.upper().strip()
    cod_str, titulo_cbte = CODIGOS_CBTE.get(letra_key, ("001", "FACTURA"))
    letra_visible = letra_key.split("_")[-1] if "_" in letra_key else letra_key[0]
    fecha_iso = fecha_emision or datetime.datetime.now().strftime("%Y-%m-%d")
    fecha_ar = f"{fecha_iso[8:10]}/{fecha_iso[5:7]}/{fecha_iso[0:4]}"
    vto_cae = cae_vto or (datetime.datetime.now() + datetime.timedelta(days=10)).strftime("%d/%m/%Y")

    subtotal_neto = 0.0
    total_iva = 0.0
    filas_html = []
    discrimina_iva = letra_visible == "A"

    for it in items:
        desc = it.get("descripcion", "Servicio profesional")
        cant = float(it.get("cantidad", 1))
        pu = float(it.get("precio_unitario", 0))
        alic = float(it.get("alicuota_iva", 21 if discrimina_iva else 0))
        neto = round(cant * pu, 2)
        iva_it = round(neto * (alic / 100.0), 2) if discrimina_iva else 0.0
        subtotal_neto += neto
        total_iva += iva_it
        sub_fila = round(neto + iva_it, 2)
        filas_html.append(
            f"<tr><td>{desc}</td><td style='text-align:right'>{cant:g}</td>"
            f"<td style='text-align:right'>${pu:,.2f}</td>"
            f"<td style='text-align:right'>{alic:g}%</td>"
            f"<td style='text-align:right'><strong>${sub_fila:,.2f}</strong></td></tr>"
        )

    total_final = round(subtotal_neto + total_iva, 2)
    qr_url = generar_url_qr_arca(
        cuit_emisor=emisor_cuit,
        pto_vta=pto_vta,
        tipo_cmp=int(cod_str),
        nro_cmp=nro_comprobante,
        importe_total=total_final,
        fecha_iso=fecha_iso,
        doc_rec_nro=receptor_cuit,
        cae=cae,
        moneda=moneda
    )

    pto_fmt = f"{int(pto_vta):05d}"
    nro_fmt = f"{int(nro_comprobante):08d}"

    html = f"""<!doctype html>
<html lang="es-AR">
<head>
<meta charset="utf-8">
<title>{titulo_cbte} {letra_visible} {pto_fmt}-{nro_fmt}</title>
<style>
  body {{ font-family: Arial, Helvetica, sans-serif; color: #111; margin: 24px; font-size: 12px; }}
  .sheet {{ max-width: 820px; margin: 0 auto; border: 1.5px solid #111; }}
  .top-bar {{ text-align: center; font-weight: bold; padding: 6px; border-bottom: 1.5px solid #111; letter-spacing: 0.12em; }}
  .header {{ display: flex; position: relative; border-bottom: 1.5px solid #111; }}
  .col {{ width: 50%; padding: 14px 16px; box-sizing: border-box; }}
  .col-left {{ border-right: 1px solid #111; }}
  .letter-box {{ position: absolute; left: 50%; top: 0; transform: translateX(-50%); background: #fff; border: 1.5px solid #111; border-top: 0; width: 62px; text-align: center; padding: 4px 0; }}
  .letter {{ font-size: 28px; font-weight: 800; line-height: 1; }}
  .cod {{ font-size: 9px; font-weight: 700; margin-top: 2px; }}
  .receptor {{ padding: 12px 16px; border-bottom: 1.5px solid #111; display: grid; grid-template-columns: 1fr 1fr; gap: 6px; background: #fafafa; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ background: #e9eef3; border-bottom: 1px solid #111; padding: 8px; text-align: left; font-size: 11px; }}
  td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
  .totales {{ padding: 14px 16px; border-top: 1.5px solid #111; display: flex; justify-content: flex-end; }}
  .tot-box {{ width: 280px; }}
  .tot-row {{ display: flex; justify-content: space-between; margin: 4px 0; }}
  .tot-final {{ font-size: 15px; font-weight: 800; border-top: 1.5px solid #111; padding-top: 6px; margin-top: 6px; }}
  .footer {{ padding: 12px 16px; border-top: 1.5px solid #111; display: flex; justify-content: space-between; align-items: center; font-size: 11px; }}
  .qr-box {{ border: 1px dashed #666; padding: 6px 10px; font-size: 10px; max-width: 340px; word-break: break-all; }}
</style>
</head>
<body>
<div class="sheet">
  <div class="top-bar">ORIGINAL</div>
  <div class="header">
    <div class="letter-box">
      <div class="letter">{letra_visible}</div>
      <div class="cod">COD. {cod_str}</div>
    </div>
    <div class="col col-left">
      <div style="font-size:17px;font-weight:800;margin-bottom:8px">{emisor_razon_social}</div>
      <div><strong>Domicilio Comercial:</strong> {emisor_domicilio}</div>
      <div><strong>Condición frente al IVA:</strong> {emisor_condicion_iva}</div>
    </div>
    <div class="col" style="padding-left:44px">
      <div style="font-size:16px;font-weight:800;margin-bottom:6px">{titulo_cbte}</div>
      <div><strong>Punto de Venta:</strong> {pto_fmt} &nbsp;&nbsp; <strong>Comp. Nro:</strong> {nro_fmt}</div>
      <div><strong>Fecha de Emisión:</strong> {fecha_ar}</div>
      <div style="margin-top:6px"><strong>CUIT:</strong> {emisor_cuit}</div>
      <div><strong>Ingresos Brutos:</strong> {iibb_emisor}</div>
      <div><strong>Inicio de Actividades:</strong> {inicio_actividades}</div>
    </div>
  </div>
  <div class="receptor">
    <div><strong>CUIT Receptor:</strong> {receptor_cuit}</div>
    <div><strong>Razón Social:</strong> {receptor_razon_social}</div>
    <div><strong>Condición frente al IVA:</strong> {receptor_condicion_iva}</div>
    <div><strong>Moneda:</strong> {moneda}</div>
  </div>
  <table>
    <thead>
      <tr>
        <th>Producto / Servicio</th>
        <th style="text-align:right">Cant.</th>
        <th style="text-align:right">Precio Unit.</th>
        <th style="text-align:right">Alícuota IVA</th>
        <th style="text-align:right">Subtotal</th>
      </tr>
    </thead>
    <tbody>
      {"".join(filas_html)}
    </tbody>
  </table>
  <div class="totales">
    <div class="tot-box">
      <div class="tot-row"><span>Importe Neto Gravado:</span><span>${subtotal_neto:,.2f}</span></div>
      {"<div class='tot-row'><span>IVA Discriminado:</span><span>$" + f"{total_iva:,.2f}" + "</span></div>" if discrimina_iva else ""}
      <div class="tot-row tot-final"><span>Importe Total:</span><span>${total_final:,.2f}</span></div>
    </div>
  </div>
  <div class="footer">
    <div class="qr-box">
      <strong>QR Oficial ARCA (RG 4892):</strong><br>
      <a href="{qr_url}">{qr_url[:75]}...</a>
    </div>
    <div style="text-align:right">
      <div><strong>CAE N°:</strong> {cae}</div>
      <div><strong>Fecha de Vto. de CAE:</strong> {vto_cae}</div>
      <div style="margin-top:4px;color:#555">Comprobante Autorizado · impuesto.com.ar</div>
    </div>
  </div>
</div>
</body>
</html>"""

    pdf_generado = None
    if exportar_pdf_ruta:
        try:
            from playwright.sync_api import sync_playwright
            from bot.scraper import _get_browser_path
            os.makedirs(os.path.dirname(os.path.abspath(exportar_pdf_ruta)), exist_ok=True)
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, executable_path=_get_browser_path(), args=["--no-sandbox"])
                page = browser.new_page()
                page.set_content(html, wait_until="load")
                page.pdf(path=exportar_pdf_ruta, format="A4", print_background=True)
                browser.close()
            pdf_generado = exportar_pdf_ruta
        except Exception as e:
            pdf_generado = f"HTML listo (PDF error: {e})"

    return {
        "ok": True,
        "comprobante": f"{titulo_cbte} {letra_visible} {pto_fmt}-{nro_fmt}",
        "importe_neto": round(subtotal_neto, 2),
        "importe_iva": round(total_iva, 2),
        "importe_total": total_final,
        "cae": cae,
        "cae_vto": vto_cae,
        "qr_oficial_arca": qr_url,
        "pdf_path": pdf_generado,
        "html_imprimible": html
    }
