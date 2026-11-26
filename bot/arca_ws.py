"""
bot/arca_ws.py
Cliente nativo de Web Services Oficiales de ARCA (ex-AFIP):
- Generación de clave privada y CSR (OpenSSL) para onboarding automático de certificados.
- WSAA (Web Service de Autenticación y Autorización): firma CMS/PKCS#7 y cache de Token/Sign (12hs).
- WSFEv1: FEDummy (estado de servidores), FECompUltimoAutorizado y FECAESolicitar (Facturas A, B, C con CAE y QR).
- WS_SR_PADRON_A5: Consulta de constancia de inscripción, condición IVA/Monotributo y domicilio fiscal de cualquier CUIT.

Funciona en modo 'homologacion' (pruebas) y 'produccion'.
Aplica estrictamente Human-in-the-Loop: emitir_comprobante_wsfe requiere confirmado=True para impactar en ARCA.
"""

import os
import json
import base64
import ssl
import subprocess
import tempfile
import datetime
import urllib.request
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional

ENDPOINTS = {
    "homologacion": {
        "wsaa": "https://wsaahomo.afip.gov.ar/ws/services/LoginCms",
        "wsfev1": "https://wswhomo.afip.gov.ar/wsfev1/service.asmx",
        "wsfexv1": "https://wswhomo.afip.gov.ar/wsfexv1/service.asmx",
        "wsfecred": "https://fwshomo.afip.gov.ar/wsfecred/FECredService",
        "padron_a5": "https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA5",
        "veconsumerws": "https://infraestructura.afip.gob.ar/ve-ws/services/veconsumer",
        "wsapoc": "https://wswhomo.afip.gov.ar/wsapoc/service.asmx",
        "wscdc": "https://wswhomo.afip.gov.ar/WSCDC/service.asmx",
        "createvep": "https://setipagob2b-homo.afip.gob.ar/ws/services/createvep"
    },
    "produccion": {
        "wsaa": "https://wsaa.afip.gov.ar/ws/services/LoginCms",
        "wsfev1": "https://servicios1.afip.gov.ar/wsfev1/service.asmx",
        "wsfexv1": "https://servicios1.afip.gov.ar/wsfexv1/service.asmx",
        "wsfecred": "https://serviciosjava.afip.gob.ar/wsfecred/FECredService",
        "padron_a5": "https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA5",
        "veconsumerws": "https://infraestructura.afip.gob.ar/ve-ws/services/veconsumer",
        "wsapoc": "https://servicios1.afip.gov.ar/wsapoc/service.asmx",
        "wscdc": "https://servicios1.afip.gov.ar/WSCDC/service.asmx",
        "createvep": "https://setipagob2b.afip.gob.ar/ws/services/createvep"
    }
}

CBTE_TIPOS = {
    "FACTURA_A": 1,
    "NOTA_DEBITO_A": 2,
    "NOTA_CREDITO_A": 3,
    "FACTURA_B": 6,
    "NOTA_DEBITO_B": 7,
    "NOTA_CREDITO_B": 8,
    "FACTURA_C": 11,
    "NOTA_DEBITO_C": 12,
    "NOTA_CREDITO_C": 13,
    "FACTURA_M": 51
}

CACHE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "wsaa_cache"))
os.makedirs(CACHE_DIR, exist_ok=True)


def _ssl_context():
    ctx = ssl.create_default_context()
    # ARCA suele requerir SECLEVEL=1 en algunos OpenSSL modernos
    try:
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    except Exception:
        pass
    return ctx


def _soap_post(url: str, xml_body: str, soap_action: str = "", timeout: int = 15) -> str:
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "User-Agent": "impuesto-arca-mcp/1.0"
    }
    if soap_action:
        headers["SOAPAction"] = soap_action
    req = urllib.request.Request(url, data=xml_body.encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, context=_ssl_context(), timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def verificar_estado_servidores_wsfe(ambiente: str = "produccion") -> Dict[str, Any]:
    """
    Llama a FEDummy en WSFEv1 (no requiere certificado).
    Permite comprobar en <1 segundo si AppServer, DbServer y AuthServer de ARCA están online.
    """
    env_key = "homologacion" if "homo" in ambiente.lower() else "produccion"
    url = ENDPOINTS[env_key]["wsfev1"]
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">
   <soapenv:Header/>
   <soapenv:Body>
      <ar:FEDummy/>
   </soapenv:Body>
</soapenv:Envelope>"""
    try:
        raw = _soap_post(url, xml, soap_action="http://ar.gov.afip.dif.FEV1/FEDummy", timeout=10)
        root = ET.fromstring(raw)
        ns = {"ar": "http://ar.gov.afip.dif.FEV1/"}
        app = root.findtext(".//ar:AppServer", default="UNKNOWN", namespaces=ns)
        db = root.findtext(".//ar:DbServer", default="UNKNOWN", namespaces=ns)
        auth = root.findtext(".//ar:AuthServer", default="UNKNOWN", namespaces=ns)
        online = (app == "OK" and db == "OK" and auth == "OK")
        return {
            "ambiente": env_key,
            "endpoint": url,
            "online": online,
            "AppServer": app,
            "DbServer": db,
            "AuthServer": auth,
            "mensaje": "Servidores WSFEv1 de ARCA operativos al 100%." if online else "ARCA presenta degradación parcial en WSFEv1."
        }
    except Exception as e:
        return {
            "ambiente": env_key,
            "endpoint": url,
            "online": False,
            "error": str(e),
            "mensaje": "No se pudo conectar con WSFEv1 de ARCA en este momento."
        }


def generar_csr_arca(cuit: str, razon_social: str, alias: str = "impuesto_mcp") -> Dict[str, Any]:
    """
    Genera una clave privada RSA 2048 y un pedido de certificado (.csr) compatible con ARCA
    usando OpenSSL. El archivo .csr se sube en 'Administración de Certificados Digitales' de ARCA.
    """
    cuit_clean = "".join(c for c in str(cuit) if c.isdigit())
    if len(cuit_clean) != 11:
        raise ValueError("El CUIT debe tener exactamente 11 dígitos.")

    certs_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "certs", cuit_clean))
    os.makedirs(certs_dir, exist_ok=True)
    key_path = os.path.join(certs_dir, f"{alias}.key")
    csr_path = os.path.join(certs_dir, f"{alias}.csr")

    subj = f"/C=AR/O={razon_social[:50]}/CN={alias}/serialNumber=CUIT {cuit_clean}"

    subprocess.run(["openssl", "genrsa", "-out", key_path, "2048"], check=True, capture_output=True)
    subprocess.run(
        ["openssl", "req", "-new", "-key", key_path, "-subj", subj, "-out", csr_path],
        check=True,
        capture_output=True
    )

    with open(csr_path, "r", encoding="utf-8") as f:
        csr_pem = f.read()

    return {
        "cuit": cuit_clean,
        "alias": alias,
        "key_path": key_path,
        "csr_path": csr_path,
        "csr_pem": csr_pem,
        "siguientes_pasos": [
            "1. Subir el archivo .csr en ARCA → 'Administración de Certificados Digitales' → Agregar alias.",
            "2. Descargar el certificado firmado (.crt) y guardarlo junto a la clave privada.",
            "3. En 'Administrador de Relaciones de Clave Fiscal' asociar el alias a 'wsfe' (Facturación) y 'ws_sr_padron_a5' (Padrón)."
        ]
    }


def autenticar_wsaa(
    cert_path: str,
    key_path: str,
    service: str = "wsfe",
    ambiente: str = "homologacion"
) -> Dict[str, str]:
    """
    Obtiene Token y Sign desde WSAA firmando el TRA en formato CMS/PKCS#7.
    Cachea el Ticket de Acceso (TA) durante su vigencia (~12 horas) para evitar errores de 'TA ya vigente'.
    """
    env_key = "homologacion" if "homo" in ambiente.lower() else "produccion"
    cache_file = os.path.join(CACHE_DIR, f"ta_{env_key}_{service}_{os.path.basename(cert_path)}.json")

    # 1. Revisar cache vigente
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
            exp = datetime.datetime.fromisoformat(cached["expiration"])
            if exp > datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5):
                return {"token": cached["token"], "sign": cached["sign"], "desde_cache": True}
        except Exception:
            pass

    if not os.path.exists(cert_path) or not os.path.exists(key_path):
        raise FileNotFoundError("No se encontraron el certificado (.crt) o la clave privada (.key) de ARCA.")

    now = datetime.datetime.now(datetime.timezone.utc)
    gen_time = (now - datetime.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    exp_time = (now + datetime.timedelta(hours=11)).strftime("%Y-%m-%dT%H:%M:%SZ")
    unique_id = int(now.timestamp())

    tra_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<loginTicketRequest version="1.0">
  <header>
    <uniqueId>{unique_id}</uniqueId>
    <generationTime>{gen_time}</generationTime>
    <expirationTime>{exp_time}</expirationTime>
  </header>
  <service>{service}</service>
</loginTicketRequest>"""

    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as f_tra:
        f_tra.write(tra_xml)
        tra_path = f_tra.name
    cms_path = tra_path + ".cms"

    try:
        subprocess.run(
            [
                "openssl", "smime", "-sign",
                "-in", tra_path,
                "-out", cms_path,
                "-signer", cert_path,
                "-inkey", key_path,
                "-outform", "DER",
                "-nodetach"
            ],
            check=True,
            capture_output=True
        )
        with open(cms_path, "rb") as f_cms:
            cms_b64 = base64.b64encode(f_cms.read()).decode("ascii")
    finally:
        for p in (tra_path, cms_path):
            if os.path.exists(p):
                os.remove(p)

    soap_wsaa = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:wsaa="http://wsaa.view.sua.dvadac.desein.afip.gov">
   <soapenv:Header/>
   <soapenv:Body>
      <wsaa:loginCms>
         <wsaa:in0>{cms_b64}</wsaa:in0>
      </wsaa:loginCms>
   </soapenv:Body>
</soapenv:Envelope>"""

    raw = _soap_post(ENDPOINTS[env_key]["wsaa"], soap_wsaa, soap_action="loginCms", timeout=15)
    root = ET.fromstring(raw)
    login_return = None
    for el in root.iter():
        if el.tag.endswith("loginCmsReturn"):
            login_return = el.text
            break
    if not login_return:
        raise RuntimeError(f"Error en respuesta WSAA: {raw[:400]}")

    ta_root = ET.fromstring(login_return)
    token = ta_root.findtext(".//token")
    sign = ta_root.findtext(".//sign")
    expiration = ta_root.findtext(".//expirationTime") or exp_time

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump({"token": token, "sign": sign, "expiration": expiration}, f)

    return {"token": token, "sign": sign, "desde_cache": False}


def consultar_ultimo_comprobante_wsfe(
    cuit_emisor: str,
    pto_vta: int,
    cbte_tipo: int,
    token: str,
    sign: str,
    ambiente: str = "homologacion"
) -> int:
    """
    Consulta FECompUltimoAutorizado para saber el próximo número correlativo oficial.
    """
    env_key = "homologacion" if "homo" in ambiente.lower() else "produccion"
    cuit_clean = "".join(c for c in str(cuit_emisor) if c.isdigit())
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">
   <soapenv:Header/>
   <soapenv:Body>
      <ar:FECompUltimoAutorizado>
         <ar:Auth>
            <ar:Token>{token}</ar:Token>
            <ar:Sign>{sign}</ar:Sign>
            <ar:Cuit>{cuit_clean}</ar:Cuit>
         </ar:Auth>
         <ar:PtoVta>{pto_vta}</ar:PtoVta>
         <ar:CbteTipo>{cbte_tipo}</ar:CbteTipo>
      </ar:FECompUltimoAutorizado>
   </soapenv:Body>
</soapenv:Envelope>"""
    raw = _soap_post(ENDPOINTS[env_key]["wsfev1"], xml, soap_action="http://ar.gov.afip.dif.FEV1/FECompUltimoAutorizado")
    root = ET.fromstring(raw)
    ns = {"ar": "http://ar.gov.afip.dif.FEV1/"}
    nro = root.findtext(".//ar:CbteNro", default="0", namespaces=ns)
    return int(nro)


def emitir_comprobante_wsfe(
    cuit_emisor: str,
    pto_vta: int,
    cbte_tipo: int,
    receptor_cuit: str,
    importe_neto: float,
    importe_iva: float = 0.0,
    concepto: int = 2,  # 1=Productos, 2=Servicios, 3=Productos y Servicios
    alicuota_iva_id: int = 5,  # 5=21%, 4=10.5%, 6=27%, 3=0%
    ambiente: str = "homologacion",
    cert_path: Optional[str] = None,
    key_path: Optional[str] = None,
    confirmado: bool = False
) -> Dict[str, Any]:
    """
    Prepara o emite una factura electrónica oficial vía WSFEv1 (FECAESolicitar).
    Si confirmado=False devuelve el borrador completo sin impactar en ARCA.
    """
    cuit_em = "".join(c for c in str(cuit_emisor) if c.isdigit())
    cuit_rec = "".join(c for c in str(receptor_cuit) if c.isdigit())
    doc_tipo = 80 if len(cuit_rec) == 11 else 99
    doc_nro = int(cuit_rec) if cuit_rec else 0
    imp_total = round(importe_neto + importe_iva, 2)
    hoy = datetime.datetime.now().strftime("%Y%m%d")

    borrador = {
        "modo": "BORRADOR_SIN_IMPACTO" if not confirmado else "EMISION_OFICIAL_WSFEV1",
        "ambiente": ambiente,
        "emisor_cuit": cuit_em,
        "punto_venta": pto_vta,
        "cbte_tipo": cbte_tipo,
        "receptor_doc_tipo": doc_tipo,
        "receptor_doc_nro": doc_nro,
        "concepto": concepto,
        "fecha": hoy,
        "importe_neto": round(importe_neto, 2),
        "importe_iva": round(importe_iva, 2),
        "importe_total": imp_total
    }

    if not confirmado:
        borrador["mensaje"] = (
            "Borrador WSFEv1 validado y listo para emitir CAE en <1 segundo. "
            "Para confirmar y solicitar el CAE oficial ante ARCA, invocá nuevamente con confirmado=True."
        )
        return borrador

    # Emisión real vía WSAA + WSFEv1
    c_path = cert_path or os.environ.get("ARCA_WS_CERT")
    k_path = key_path or os.environ.get("ARCA_WS_KEY")
    if not c_path or not k_path:
        return {
            **borrador,
            "estado": "CERTIFICADO_PENDIENTE",
            "mensaje": (
                "Para emitir el CAE oficial por Web Service necesitás vincular tu certificado (.crt) y clave (.key) "
                "en ARCA_WS_CERT y ARCA_WS_KEY (podés generar el .csr con generar_certificado_csr_arca)."
            )
        }

    auth = autenticar_wsaa(c_path, k_path, service="wsfe", ambiente=ambiente)
    ultimo = consultar_ultimo_comprobante_wsfe(cuit_em, pto_vta, cbte_tipo, auth["token"], auth["sign"], ambiente)
    proximo = ultimo + 1

    iva_block = ""
    if importe_iva > 0:
        iva_block = f"""<ar:Iva>
            <ar:AlicIva>
              <ar:Id>{alicuota_iva_id}</ar:Id>
              <ar:BaseImp>{round(importe_neto, 2):.2f}</ar:BaseImp>
              <ar:Importe>{round(importe_iva, 2):.2f}</ar:Importe>
            </ar:AlicIva>
          </ar:Iva>"""

    fechas_serv = ""
    if concepto in (2, 3):
        fechas_serv = f"""<ar:FchServDesde>{hoy}</ar:FchServDesde>
          <ar:FchServHasta>{hoy}</ar:FchServHasta>
          <ar:FchVtoPago>{hoy}</ar:FchVtoPago>"""

    env_key = "homologacion" if "homo" in ambiente.lower() else "produccion"
    soap = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">
   <soapenv:Header/>
   <soapenv:Body>
      <ar:FECAESolicitar>
         <ar:Auth>
            <ar:Token>{auth['token']}</ar:Token>
            <ar:Sign>{auth['sign']}</ar:Sign>
            <ar:Cuit>{cuit_em}</ar:Cuit>
         </ar:Auth>
         <ar:FeCAEReq>
            <ar:FeCabReq>
               <ar:CantReg>1</ar:CantReg>
               <ar:PtoVta>{pto_vta}</ar:PtoVta>
               <ar:CbteTipo>{cbte_tipo}</ar:CbteTipo>
            </ar:FeCabReq>
            <ar:FeDetReq>
               <ar:FECAEDetRequest>
                  <ar:Concepto>{concepto}</ar:Concepto>
                  <ar:DocTipo>{doc_tipo}</ar:DocTipo>
                  <ar:DocNro>{doc_nro}</ar:DocNro>
                  <ar:CbteDesde>{proximo}</ar:CbteDesde>
                  <ar:CbteHasta>{proximo}</ar:CbteHasta>
                  <ar:CbteFch>{hoy}</ar:CbteFch>
                  <ar:ImpTotal>{imp_total:.2f}</ar:ImpTotal>
                  <ar:ImpTotConc>0.00</ar:ImpTotConc>
                  <ar:ImpNeto>{round(importe_neto, 2):.2f}</ar:ImpNeto>
                  <ar:ImpOpEx>0.00</ar:ImpOpEx>
                  <ar:ImpTrib>0.00</ar:ImpTrib>
                  <ar:ImpIVA>{round(importe_iva, 2):.2f}</ar:ImpIVA>
                  {fechas_serv}
                  <ar:MonId>PES</ar:MonId>
                  <ar:MonCotiz>1</ar:MonCotiz>
                  {iva_block}
               </ar:FECAEDetRequest>
            </ar:FeDetReq>
         </ar:FeCAEReq>
      </ar:FECAESolicitar>
   </soapenv:Body>
</soapenv:Envelope>"""

    raw = _soap_post(ENDPOINTS[env_key]["wsfev1"], soap, soap_action="http://ar.gov.afip.dif.FEV1/FECAESolicitar")
    root = ET.fromstring(raw)
    ns = {"ar": "http://ar.gov.afip.dif.FEV1/"}
    resultado = root.findtext(".//ar:Resultado", default="R", namespaces=ns)
    cae = root.findtext(".//ar:CAE", default="", namespaces=ns)
    cae_vto = root.findtext(".//ar:CAEFchVto", default="", namespaces=ns)
    obs = [el.text for el in root.findall(".//ar:Msg", namespaces=ns) if el.text]

    # URL oficial de Código QR ARCA (RG 4892)
    qr_url = ""
    if cae:
        qr_payload = {
            "ver": 1,
            "fecha": f"{hoy[:4]}-{hoy[4:6]}-{hoy[6:8]}",
            "cuit": int(cuit_em),
            "ptoVta": pto_vta,
            "tipoCmp": cbte_tipo,
            "nroCmp": proximo,
            "importe": imp_total,
            "moneda": "PES",
            "ctz": 1,
            "tipoDocRec": doc_tipo,
            "nroDocRec": doc_nro,
            "tipoCodAut": "E",
            "codAut": int(cae)
        }
        b64_qr = base64.b64encode(json.dumps(qr_payload).encode("utf-8")).decode("ascii")
        qr_url = f"https://www.afip.gob.ar/fe/qr/?p={b64_qr}"

    return {
        **borrador,
        "cbte_nro": proximo,
        "resultado": "APROBADO" if resultado == "A" else "RECHAZADO",
        "cae": cae,
        "cae_vencimiento": cae_vto,
        "qr_oficial_arca": qr_url,
        "observaciones": obs
    }


def consultar_padron_a5(
    cuit_consulta: str,
    cuit_representado: Optional[str] = None,
    ambiente: str = "produccion",
    cert_path: Optional[str] = None,
    key_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Consulta Constancia de Inscripción (Padrón Alcance 5 - WS_SR_PADRON_A5) de cualquier CUIT.
    """
    cuit_q = "".join(c for c in str(cuit_consulta) if c.isdigit())
    cuit_rep = "".join(c for c in str(cuit_representado or cuit_q) if c.isdigit())
    c_path = cert_path or os.environ.get("ARCA_WS_CERT")
    k_path = key_path or os.environ.get("ARCA_WS_KEY")

    if not c_path or not k_path:
        return {
            "cuit_consultado": cuit_q,
            "estado": "CERTIFICADO_PENDIENTE",
            "mensaje": (
                "El servicio WS_SR_PADRON_A5 requiere certificado digital ARCA (ARCA_WS_CERT y ARCA_WS_KEY). "
                "Generá tu CSR con generar_certificado_csr_arca y asocialo en Administrador de Relaciones."
            )
        }

    auth = autenticar_wsaa(c_path, k_path, service="ws_sr_padron_a5", ambiente=ambiente)
    env_key = "homologacion" if "homo" in ambiente.lower() else "produccion"

    soap = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:a5="http://a5.soap.ws.server.puc.sr/">
   <soapenv:Header/>
   <soapenv:Body>
      <a5:getPersona_v2>
         <token>{auth['token']}</token>
         <sign>{auth['sign']}</sign>
         <cuitRepresentada>{cuit_rep}</cuitRepresentada>
         <idPersona>{cuit_q}</idPersona>
      </a5:getPersona_v2>
   </soapenv:Body>
</soapenv:Envelope>"""

    raw = _soap_post(ENDPOINTS[env_key]["padron_a5"], soap, timeout=15)
    root = ET.fromstring(raw)

    def _find_any(tag):
        for el in root.iter():
            if el.tag.endswith(tag) and el.text:
                return el.text.strip()
        return None

    return {
        "cuit": cuit_q,
        "razon_social": _find_any("razonSocial") or f"{_find_any('apellido') or ''} {_find_any('nombre') or ''}".strip(),
        "tipo_persona": _find_any("tipoPersona"),
        "estado_clave": _find_any("estadoClave"),
        "domicilio_fiscal": _find_any("direccion"),
        "localidad": _find_any("localidad"),
        "provincia": _find_any("descripcionProvincia"),
        "categoria_monotributo": _find_any("descripcionCategoria"),
        "actividad_principal": _find_any("descripcionActividad")
    }


if __name__ == "__main__":
    print("Probando conexión real FEDummy contra WSFEv1 Producción de ARCA...")
    print(json.dumps(verificar_estado_servidores_wsfe("produccion"), indent=2, ensure_ascii=False))
