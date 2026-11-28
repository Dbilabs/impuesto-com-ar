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
import hashlib
import ssl
import logging
import subprocess
import tempfile
import datetime
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("impuesto.arca_ws")

try:
    from zoneinfo import ZoneInfo
    AR_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
except Exception:
    AR_TZ = datetime.timezone(datetime.timedelta(hours=-3))


def fecha_hoy_arca(now: Optional[datetime.datetime] = None) -> str:
    """Devuelve YYYYMMDD en hora oficial de Argentina (America/Argentina/Buenos_Aires) para CbteFch (N4-d)."""
    if now is None:
        dt_ar = datetime.datetime.now(AR_TZ)
    elif now.tzinfo is None:
        dt_ar = now.replace(tzinfo=datetime.timezone.utc).astimezone(AR_TZ)
    else:
        dt_ar = now.astimezone(AR_TZ)
    return dt_ar.strftime("%Y%m%d")

class CertificadoPendienteError(RuntimeError):
    """Faltan ARCA_WS_CERT / ARCA_WS_KEY para operar Web Services oficiales."""


class WsaaAlreadyAuthenticatedError(RuntimeError):
    """WSAA rechazó LoginCms con coe.alreadyAuthenticated (ya existe un TA vigente para ese certificado y servicio)."""


class WsapocResponseError(RuntimeError):
    """Error explícito o XML malformado en respuesta de WSAPOC (nunca interpretar como 'no apócrifo')."""


class WsapocUnavailableError(RuntimeError):
    """WSAPOC temporalmente no disponible (red/timeout/HTTP 5xx); habilita fallback a Playwright."""


_WSAPOC_CACHE: "OrderedDict[str, tuple[float, Dict[str, Any]]]" = OrderedDict()
WSAPOC_CACHE_TTL_SEC = 86400.0  # 24 horas por CUIT consultado
WSAPOC_CACHE_MAX_SIZE = 10000   # Tope LRU en memoria (W2)


def _wsaa_cache_dir() -> Path:
    """W1: almacena tickets WSAA dentro del volumen persistente (<VAULT_DIR>/wsaa_cache), nunca en <repo>/data."""
    from . import boveda_segura as bv
    d = bv.VAULT_DIR / "wsaa_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def migrar_tickets_wsaa_legados(legacy_dir: Optional[Path] = None) -> int:
    """Residual P3 de W1: migra tickets WSAA legados (<repo>/data/wsaa_cache/ta_*.json) vigentes a <VAULT_DIR>/wsaa_cache/*.enc."""
    from . import boveda_segura as bv
    src_dir = legacy_dir or (Path(__file__).resolve().parent.parent / "data" / "wsaa_cache")
    if not src_dir.exists() or not src_dir.is_dir():
        return 0
    migrated = 0
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    dst_dir = _wsaa_cache_dir()
    for p in list(src_dir.glob("ta_*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            exp_raw = str(data.get("expiration") or "")
            exp = datetime.datetime.fromisoformat(exp_raw.replace("Z", "+00:00"))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=datetime.timezone.utc)
            if exp > now_utc + datetime.timedelta(minutes=5) and data.get("token") and data.get("sign"):
                dst = dst_dir / (p.stem + ".enc")
                if not dst.exists():
                    bv._write_enc_json(dst, {"token": data["token"], "sign": data["sign"], "expiration": exp_raw})
                    migrated += 1
            p.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning(f"[WSAA migración] No se pudo migrar {p.name}: {exc}")
    return migrated

ENDPOINTS = {
    "homologacion": {
        "wsaa": "https://wsaahomo.afip.gov.ar/ws/services/LoginCms",
        "wsfev1": "https://wswhomo.afip.gov.ar/wsfev1/service.asmx",
        "wsfexv1": "https://wswhomo.afip.gov.ar/wsfexv1/service.asmx",
        "wsfecred": "https://fwshomo.afip.gov.ar/wsfecred/FECredService",
        "padron_a5": "https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA5",
        "veconsumerws": "https://infraestructura.afip.gob.ar/ve-ws/services/veconsumer",
        # Confirmado contra WSDL vivo (200 OK): https://eapoc-ws-qaext.afip.gob.ar/service.asmx?WSDL (op: GetPublicacionAPOC)
        "wsapoc": "https://eapoc-ws-qaext.afip.gob.ar/service.asmx",
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
        # Confirmado contra WSDL vivo (200 OK): https://eapoc-ws.afip.gob.ar/service.asmx?WSDL (op: GetPublicacionAPOC)
        "wsapoc": "https://eapoc-ws.afip.gob.ar/service.asmx",
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

# W1: tickets WSAA ahora se guardan cifrados en <VAULT_DIR>/wsaa_cache (vía _wsaa_cache_dir())
CACHE_DIR = None


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


def _derivar_huella_pem(pem_str: str) -> str:
    return hashlib.sha256((pem_str or "").strip().encode("utf-8")).hexdigest()[:12]


def _firmar_tra_en_memoria(tra_xml: str, cert_pem: str, key_pem: str) -> str:
    """Fase 3.5: firma TRA en formato CMS/PKCS#7 DER completamente en memoria usando cryptography (cero archivos temporales de clave)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.serialization import pkcs7

    cert = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
    priv_key = serialization.load_pem_private_key(key_pem.encode("utf-8"), password=None)
    der_bytes = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(tra_xml.encode("utf-8"))
        .add_signer(cert, priv_key, hashes.SHA256())
        .sign(serialization.Encoding.DER, [])
    )
    return base64.b64encode(der_bytes).decode("ascii")


def evaluar_vencimiento_cert_pem(cert_pem: str, dias_alerta: int = 30) -> Dict[str, Any]:
    """Inspecciona vigencia de un certificado PEM y genera alerta si faltan <= 30 días (Fase 3.5)."""
    from cryptography import x509
    cert = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
    now = datetime.datetime.now(datetime.timezone.utc)
    n_before = getattr(cert, "not_valid_before_utc", cert.not_valid_before.replace(tzinfo=datetime.timezone.utc))
    n_after = getattr(cert, "not_valid_after_utc", cert.not_valid_after.replace(tzinfo=datetime.timezone.utc))
    dias_restantes = int((n_after - now).total_seconds() // 86400)
    vigente = n_before <= now <= n_after
    alerta = None
    if vigente and dias_restantes <= dias_alerta:
        alerta = f"Tu certificado digital ARCA vence en {max(0, dias_restantes)} día(s) ({n_after.date().isoformat()}). Renovalo pronto."
    return {
        "vigente": vigente,
        "not_before": n_before.isoformat(),
        "not_after": n_after.isoformat(),
        "dias_restantes": dias_restantes,
        "alerta_vencimiento": alerta,
    }


def generar_csr_arca(
    cuit: str,
    razon_social: str,
    alias: str = "impuesto_mcp",
    owner_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fase 3.5: genera clave privada RSA 2048 y CSR en memoria con cryptography, guarda la clave privada
    cifrada en la bóveda por CUIT y devuelve ÚNICAMENTE el CSR (la clave privada nunca sale en respuestas ni logs).
    """
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from . import boveda_segura as bv

    cuit_clean = "".join(c for c in str(cuit) if c.isdigit())
    if len(cuit_clean) != 11:
        raise ValueError("El CUIT debe tener exactamente 11 dígitos.")

    priv_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_pem = priv_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "AR"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, (razon_social or "Contribuyente")[:50]),
        x509.NameAttribute(NameOID.COMMON_NAME, (alias or "impuesto_mcp")[:50]),
        x509.NameAttribute(NameOID.SERIAL_NUMBER, f"CUIT {cuit_clean}"),
    ])
    csr = x509.CertificateSigningRequestBuilder().subject_name(subject).sign(priv_key, hashes.SHA256())
    csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode("utf-8")

    guardado = bv.guardar_credenciales_cifradas(
        cuit=cuit_clean,
        key_pem=key_pem,
        owner_email=owner_email,
    )
    if not guardado.get("ok"):
        return guardado

    return {
        "ok": True,
        "cuit": cuit_clean,
        "alias": alias,
        "csr_pem": csr_pem,
        "clave_privada_resguardada": "cifrada_en_boveda",
        "siguientes_pasos": [
            "1. Subir el CSR en ARCA → 'Administración de Certificados Digitales' → Agregar alias.",
            "2. Descargar el certificado firmado (.crt) y subirlo con `cargar_certificado_wsaa_cuit`.",
            "3. En 'Administrador de Relaciones de Clave Fiscal' asociar el alias a 'wsfe', 'ws_sr_padron_a5' o 'veconsumerws'.",
        ],
    }


def cargar_certificado_cuit_wsaa(
    *,
    cuit: str,
    cert_pem: str,
    owner_email: str,
) -> Dict[str, Any]:
    """Fase 3.5: valida y guarda el .crt del contribuyente en la bóveda cifrada.
    Exige: (a) correspondencia con la clave privada guardada, (b) SERIALNUMBER=CUIT <cuit>, (c) vigencia."""
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import serialization
    from . import boveda_segura as bv

    cuit_clean = bv.normalizar_cuit(cuit)
    ok_perm, _, reason = bv.verificar_permiso_cuit(owner_email, cuit_clean, nivel="owner")
    if not ok_perm:
        return {"ok": False, "acceso_denegado": True, "error": reason}

    rec = bv.obtener_credenciales_descifradas(cuit_clean) or {}
    key_pem = (rec.get("key_pem") or "").strip()
    if not key_pem:
        return {
            "ok": False,
            "error": f"No hay clave privada generada en bóveda para el CUIT {cuit_clean}. Ejecutá primero `generar_certificado_csr_arca`.",
        }

    try:
        cert = x509.load_pem_x509_certificate((cert_pem or "").strip().encode("utf-8"))
    except Exception as exc:
        return {"ok": False, "error": f"Certificado .crt PEM inválido: {exc}"}

    # (a) Validar que el certificado corresponda a la clave privada guardada
    try:
        priv_key = serialization.load_pem_private_key(key_pem.encode("utf-8"), password=None)
        if cert.public_key().public_numbers() != priv_key.public_key().public_numbers():
            return {"ok": False, "error": "El certificado (.crt) no corresponde a la clave privada guardada en bóveda para este CUIT."}
    except Exception as exc:
        return {"ok": False, "error": f"No se pudo verificar la correspondencia con la clave privada: {exc}"}

    # (b) Validar SERIALNUMBER == CUIT <cuit>
    serial_attrs = cert.subject.get_attributes_for_oid(NameOID.SERIAL_NUMBER)
    serial_vals = [str(a.value).strip() for a in serial_attrs]
    cuit_match = any(
        "".join(ch for ch in val if ch.isdigit()) == cuit_clean and "cuit" in val.lower()
        for val in serial_vals
    )
    if not cuit_match:
        return {
            "ok": False,
            "error": f"El subject del certificado (SERIALNUMBER={serial_vals or 'ausente'}) no coincide con CUIT {cuit_clean}.",
        }

    # (c) Validar vigencia
    vig = evaluar_vencimiento_cert_pem(cert_pem)
    if not vig["vigente"]:
        return {
            "ok": False,
            "error": f"El certificado no está vigente (validez: {vig['not_before']} a {vig['not_after']}).",
        }

    res_save = bv.guardar_credenciales_cifradas(
        cuit=cuit_clean,
        cert_pem=cert_pem.strip(),
        owner_email=owner_email,
    )
    if not res_save.get("ok"):
        return res_save

    out = {
        "ok": True,
        "cuit": cuit_clean,
        "tiene_wsaa": True,
        "huella_certificado": _derivar_huella_pem(cert_pem),
        "valido_hasta": vig["not_after"],
        "dias_restantes": vig["dias_restantes"],
        "mensaje": f"Certificado WSAA propio validado y guardado cifrado para el CUIT {cuit_clean}.",
    }
    if vig["alerta_vencimiento"]:
        out["alerta_vencimiento"] = vig["alerta_vencimiento"]
    return out


def resolver_credenciales_wsaa_para_cuit(
    cuit: str,
    cert_path: Optional[str] = None,
    key_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Fase 3.5: resuelve certificado propio del CUIT desde bóveda, o fallback al certificado global delegado."""
    from . import boveda_segura as bv
    cuit_clean = bv.normalizar_cuit(cuit)
    if not cert_path and not key_path and len(cuit_clean) == 11:
        try:
            rec = bv.obtener_credenciales_descifradas(cuit_clean) or {}
            c_pem = (rec.get("cert_pem") or "").strip()
            k_pem = (rec.get("key_pem") or "").strip()
            if c_pem and k_pem:
                vig = evaluar_vencimiento_cert_pem(c_pem)
                if vig["vigente"]:
                    return {
                        "fuente_certificado": "propio",
                        "cuit": cuit_clean,
                        "cert_pem": c_pem,
                        "key_pem": k_pem,
                        "alerta_vencimiento": vig["alerta_vencimiento"],
                    }
        except bv.VaultKeyMismatchError:
            raise
        except Exception:
            pass

    c_path = cert_path or os.environ.get("ARCA_WS_CERT")
    k_path = key_path or os.environ.get("ARCA_WS_KEY")
    if not c_path or not k_path:
        raise CertificadoPendienteError(
            "Para emitir el CAE oficial por Web Service necesitás vincular tu certificado (.crt) y clave (.key) "
            "en ARCA_WS_CERT y ARCA_WS_KEY (o generar tu certificado propio con generar_certificado_csr_arca)."
        )
    return {
        "fuente_certificado": "global_delegado",
        "cuit": cuit_clean,
        "cert_path": c_path,
        "key_path": k_path,
        "alerta_vencimiento": None,
    }


def autenticar_wsaa(
    cert_path: Optional[str] = None,
    key_path: Optional[str] = None,
    service: str = "wsfe",
    ambiente: str = "homologacion",
    *,
    cuit: str = "",
    cert_pem: Optional[str] = None,
    key_pem: Optional[str] = None,
) -> Dict[str, str]:
    """
    Obtiene Token y Sign desde WSAA firmando el TRA en formato CMS/PKCS#7.
    W1 + Fase 3.5:
      - Soporta certificado/clave en memoria (`cert_pem` + `key_pem`) sin archivos temporales.
      - Cachea el Ticket de Acceso (TA) cifrado en <VAULT_DIR>/wsaa_cache aislado por
        (cuit, env, service, huella_certificado) con permisos 0600.
      - Detecta `coe.alreadyAuthenticated` con WsaaAlreadyAuthenticatedError por clave.
    """
    from . import boveda_segura as bv
    env_key = "homologacion" if "homo" in ambiente.lower() else "produccion"
    cuit_clean = bv.normalizar_cuit(cuit)

    if cert_pem and key_pem:
        cert_huella = _derivar_huella_pem(cert_pem)
        cache_name = f"ta_{cuit_clean or 'global'}_{env_key}_{service}_{cert_huella}.enc"
    else:
        cert_huella = os.path.basename(cert_path or "global")
        if cuit_clean:
            cache_name = f"ta_{cuit_clean}_{env_key}_{service}_{cert_huella}.enc"
        else:
            cache_name = f"ta_{env_key}_{service}_{cert_huella}.enc"
    cache_path = _wsaa_cache_dir() / cache_name

    # 1. Revisar cache cifrado vigente en volumen
    if cache_path.exists():
        try:
            cached = bv._read_enc_json(cache_path, {})
            if isinstance(cached, dict) and cached.get("expiration") and cached.get("token") and cached.get("sign"):
                exp = datetime.datetime.fromisoformat(str(cached["expiration"]).replace("Z", "+00:00"))
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=datetime.timezone.utc)
                if exp > datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5):
                    return {"token": cached["token"], "sign": cached["sign"], "desde_cache": True}
        except bv.VaultKeyMismatchError:
            raise
        except Exception:
            pass

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

    if cert_pem and key_pem:
        cms_b64 = _firmar_tra_en_memoria(tra_xml, cert_pem, key_pem)
    else:
        if not cert_path or not key_path or not os.path.exists(cert_path) or not os.path.exists(key_path):
            raise FileNotFoundError("No se encontraron el certificado (.crt) o la clave privada (.key) de ARCA.")
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

    try:
        raw = _soap_post(ENDPOINTS[env_key]["wsaa"], soap_wsaa, soap_action="loginCms", timeout=15)
    except urllib.error.HTTPError as http_err:
        body = ""
        try:
            body = http_err.read().decode("utf-8", errors="ignore")
        except Exception:
            pass
        if "alreadyauthenticated" in body.lower():
            logger.error(f"[WSAA ALERTA] coe.alreadyAuthenticated para cuit={cuit_clean or 'global'} service={service} env={env_key} cert={cert_huella}.")
            raise WsaaAlreadyAuthenticatedError(
                f"WSAA rechazó LoginCms con coe.alreadyAuthenticated para '{service}' ({env_key}, cuit={cuit_clean or 'global'})."
            ) from http_err
        raise

    if "alreadyauthenticated" in (raw or "").lower():
        logger.error(f"[WSAA ALERTA] coe.alreadyAuthenticated para cuit={cuit_clean or 'global'} service={service} env={env_key} cert={cert_huella}.")
        raise WsaaAlreadyAuthenticatedError(
            f"WSAA rechazó LoginCms con coe.alreadyAuthenticated para '{service}' ({env_key}, cuit={cuit_clean or 'global'})."
        )

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

    bv._write_enc_json(cache_path, {"token": token, "sign": sign, "expiration": expiration})
    return {"token": token, "sign": sign, "desde_cache": False}


def autenticar_wsaa_para_cuit(
    cuit: str,
    service: str = "wsfe",
    ambiente: str = "homologacion",
    cert_path: Optional[str] = None,
    key_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Autentica WSAA usando el certificado propio del CUIT si existe en bóveda, o fallback global delegado."""
    cred = resolver_credenciales_wsaa_para_cuit(cuit, cert_path=cert_path, key_path=key_path)
    ta = autenticar_wsaa(
        cert_path=cred.get("cert_path"),
        key_path=cred.get("key_path"),
        service=service,
        ambiente=ambiente,
        cuit=cred["cuit"] if cred["fuente_certificado"] == "propio" else "",
        cert_pem=cred.get("cert_pem"),
        key_pem=cred.get("key_pem"),
    )
    ta["fuente_certificado"] = cred["fuente_certificado"]
    if cred.get("alerta_vencimiento"):
        ta["alerta_vencimiento"] = cred["alerta_vencimiento"]
    return ta


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
    errs = [
        f"{el.findtext('ar:Code', default='', namespaces=ns)}:{el.findtext('ar:Msg', default='', namespaces=ns)}"
        for el in root.findall(".//ar:Errors/ar:Err", namespaces=ns)
    ]
    if errs:
        raise RuntimeError(f"WSFE FECompUltimoAutorizado error: {'; '.join(errs)}")
    nro_el = root.find(".//ar:CbteNro", namespaces=ns)
    if nro_el is None or nro_el.text is None or not str(nro_el.text).strip().isdigit():
        raise RuntimeError(f"WSFE FECompUltimoAutorizado sin CbteNro válido: {raw[:300]}")
    return int(str(nro_el.text).strip())


def consultar_comprobante_wsfe(
    cuit_emisor: str,
    pto_vta: int,
    cbte_tipo: int,
    cbte_nro: int,
    token: str,
    sign: str,
    ambiente: str = "homologacion",
) -> Optional[Dict[str, Any]]:
    """Consulta FECompConsultar en WSFEv1 para verificar/adoptar un comprobante ya autorizado (N4).
    N4-g: devuelve None SOLO si ARCA informa código 602 (sin resultados); lanza RuntimeError ante cualquier otro error."""
    env_key = "homologacion" if "homo" in ambiente.lower() else "produccion"
    cuit_clean = "".join(c for c in str(cuit_emisor) if c.isdigit())
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ar="http://ar.gov.afip.dif.FEV1/">
   <soapenv:Header/>
   <soapenv:Body>
      <ar:FECompConsultar>
         <ar:Auth>
            <ar:Token>{token}</ar:Token>
            <ar:Sign>{sign}</ar:Sign>
            <ar:Cuit>{cuit_clean}</ar:Cuit>
         </ar:Auth>
         <ar:FeCompConsReq>
            <ar:CbteTipo>{int(cbte_tipo)}</ar:CbteTipo>
            <ar:CbteNro>{int(cbte_nro)}</ar:CbteNro>
            <ar:PtoVta>{int(pto_vta)}</ar:PtoVta>
         </ar:FeCompConsReq>
      </ar:FECompConsultar>
   </soapenv:Body>
</soapenv:Envelope>"""
    raw = _soap_post(ENDPOINTS[env_key]["wsfev1"], xml, soap_action="http://ar.gov.afip.dif.FEV1/FECompConsultar")
    root = ET.fromstring(raw)
    ns = {"ar": "http://ar.gov.afip.dif.FEV1/"}
    err_nodes = root.findall(".//ar:Errors/ar:Err", namespaces=ns)
    if err_nodes:
        codes = [(el.findtext("ar:Code", default="", namespaces=ns) or "").strip() for el in err_nodes]
        if all(c == "602" for c in codes):
            return None
        msgs = [f"{(el.findtext('ar:Code', default='', namespaces=ns) or '').strip()}:{(el.findtext('ar:Msg', default='', namespaces=ns) or '').strip()}" for el in err_nodes]
        raise RuntimeError(f"WSFE FECompConsultar error: {'; '.join(msgs)}")
    result_get = root.find(".//ar:ResultGet", namespaces=ns)
    if result_get is None:
        raise RuntimeError(f"WSFE FECompConsultar sin ResultGet ni código 602: {raw[:300]}")
    cae = (result_get.findtext("ar:CodAutorizacion", default="", namespaces=ns) or "").strip()
    if not cae:
        raise RuntimeError("WSFE FECompConsultar devolvió ResultGet sin CodAutorizacion (CAE).")
    imp_total_str = (result_get.findtext("ar:ImpTotal", default="0", namespaces=ns) or "0").strip()
    doc_tipo_str = (result_get.findtext("ar:DocTipo", default="0", namespaces=ns) or "0").strip()
    doc_nro_str = (result_get.findtext("ar:DocNro", default="0", namespaces=ns) or "0").strip()
    cbte_fch = (result_get.findtext("ar:CbteFch", default="", namespaces=ns) or "").strip()
    cae_vto = (result_get.findtext("ar:FchVto", default="", namespaces=ns) or "").strip()
    resultado = (result_get.findtext("ar:Resultado", default="", namespaces=ns) or "").strip()
    return {
        "cbte_nro": int(cbte_nro),
        "pto_vta": int(pto_vta),
        "cbte_tipo": int(cbte_tipo),
        "cae": cae,
        "cae_vencimiento": cae_vto,
        "imp_total": round(float(imp_total_str), 2),
        "doc_tipo": int(doc_tipo_str),
        "doc_nro": int(doc_nro_str),
        "cbte_fch": cbte_fch,
        "resultado": "APROBADO" if resultado == "A" else resultado,
    }


def obtener_ultimo_autorizado_wsfe(
    cuit_emisor: str,
    pto_vta: int,
    cbte_tipo: int,
    ambiente: str = "homologacion",
    cert_path: Optional[str] = None,
    key_path: Optional[str] = None,
) -> Optional[int]:
    """Helper de alto nivel: autentica WSAA (propio del CUIT o global delegado) y consulta FECompUltimoAutorizado."""
    auth = autenticar_wsaa_para_cuit(cuit_emisor, service="wsfe", ambiente=ambiente, cert_path=cert_path, key_path=key_path)
    return consultar_ultimo_comprobante_wsfe(cuit_emisor, pto_vta, cbte_tipo, auth["token"], auth["sign"], ambiente)


def consultar_comprobante_por_nro_wsfe(
    cuit_emisor: str,
    pto_vta: int,
    cbte_tipo: int,
    cbte_nro: int,
    ambiente: str = "homologacion",
    cert_path: Optional[str] = None,
    key_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Helper de alto nivel: autentica WSAA (propio del CUIT o global delegado) y consulta FECompConsultar."""
    auth = autenticar_wsaa_para_cuit(cuit_emisor, service="wsfe", ambiente=ambiente, cert_path=cert_path, key_path=key_path)
    return consultar_comprobante_wsfe(cuit_emisor, pto_vta, cbte_tipo, cbte_nro, auth["token"], auth["sign"], ambiente)


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
    confirmado: bool = False,
    cbte_asoc: Optional[Dict[str, Any]] = None,
    condicion_iva_receptor_id: Optional[int] = None,
    cbte_fch: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Prepara o emite comprobantes electrónicos oficiales (Facturas A/B/C/E/M/FCE, Notas de Crédito y Notas de Débito)
    desde cualquier Punto de Venta vía WSFEv1 (FECAESolicitar), incluyendo CondicionIVAReceptorId obligatorio (RG 5616).
    Si confirmado=False devuelve el borrador completo sin impactar en ARCA.
    """
    CONDICIONES_IVA_RECEPTOR = {
        1: "IVA Responsable Inscripto",
        4: "IVA Sujeto Exento",
        5: "Consumidor Final",
        6: "Responsable Monotributo",
        7: "Sujeto No Categorizado",
        8: "Proveedor del Exterior",
        9: "Cliente del Exterior",
        10: "IVA Liberado – Ley Nº 19.640",
        13: "Monotributista Social",
        15: "IVA No Alcanzado",
        16: "Monotributo Trabajador Independiente Promovido",
    }
    CBTE_NOMBRES = {
        1: "Factura A", 2: "Nota de Débito A", 3: "Nota de Crédito A",
        6: "Factura B", 7: "Nota de Débito B", 8: "Nota de Crédito B",
        11: "Factura C", 12: "Nota de Débito C", 13: "Nota de Crédito C",
        19: "Factura E (Exportación)", 20: "Nota de Débito E", 21: "Nota de Crédito E",
        51: "Factura M", 52: "Nota de Débito M", 53: "Nota de Crédito M",
        201: "Factura de Crédito Electrónica MiPyMEs (FCE A)", 202: "Nota de Débito FCE A", 203: "Nota de Crédito FCE A",
        206: "Factura de Crédito Electrónica MiPyMEs (FCE B)", 207: "Nota de Débito FCE B", 208: "Nota de Crédito FCE B",
        211: "Factura de Crédito Electrónica MiPyMEs (FCE C)", 212: "Nota de Débito FCE C", 213: "Nota de Crédito FCE C",
    }
    TIPOS_NC_ND = {2, 3, 7, 8, 12, 13, 20, 21, 52, 53, 202, 203, 207, 208, 212, 213}
    cuit_em = "".join(c for c in str(cuit_emisor) if c.isdigit())
    cuit_rec = "".join(c for c in str(receptor_cuit) if c.isdigit())
    doc_tipo = 80 if len(cuit_rec) == 11 else 99
    doc_nro = int(cuit_rec) if cuit_rec else 0
    imp_total = round(importe_neto + importe_iva, 2)
    hoy = (cbte_fch or "").strip() or fecha_hoy_arca()

    cond_iva_id = condicion_iva_receptor_id if condicion_iva_receptor_id is not None else (5 if doc_tipo == 99 else None)

    borrador = {
        "modo": "BORRADOR_SIN_IMPACTO" if not confirmado else "EMISION_OFICIAL_WSFEV1",
        "ambiente": ambiente,
        "emisor_cuit": cuit_em,
        "punto_venta": pto_vta,
        "cbte_tipo": cbte_tipo,
        "cbte_nombre": CBTE_NOMBRES.get(cbte_tipo, f"Comprobante Código {cbte_tipo}"),
        "comprobante_asociado": cbte_asoc,
        "receptor_doc_tipo": doc_tipo,
        "receptor_doc_nro": doc_nro,
        "condicion_iva_receptor_id": cond_iva_id,
        "condicion_iva_receptor_nombre": CONDICIONES_IVA_RECEPTOR.get(cond_iva_id) if cond_iva_id else "PENDIENTE_CONSULTA_PADRON",
        "concepto": concepto,
        "fecha": hoy,
        "importe_neto": round(importe_neto, 2),
        "importe_iva": round(importe_iva, 2),
        "importe_total": imp_total
    }
    if cond_iva_id is None:
        borrador["advertencia_rg5616"] = (
            "Obligatorio por ARCA (RG 5616): informar `condicion_iva_receptor_id` "
            "(1=RI, 4=Exento, 5=Consumidor Final, 6=Monotributo, 9=Exterior, 15=No Alcanzado). "
            "Consultá el CUIT del receptor en Padrón A5 (`consultar_padron_cuit_ws`) antes de emitir."
        )
    if cbte_tipo in TIPOS_NC_ND and not cbte_asoc:
        borrador["advertencia_nc_nd"] = (
            "ARCA exige informar el comprobante original asociado (`cbte_asoc: {tipo, pto_vta, nro}`) "
            "para emitir Notas de Crédito o Notas de Débito."
        )

    if not confirmado:
        borrador["mensaje"] = (
            "Borrador WSFEv1 validado y listo para emitir CAE en <1 segundo. "
            "Para confirmar y solicitar el CAE oficial ante ARCA, invocá nuevamente con confirmado=True."
        )
        return borrador

    # Emisión real vía WSAA (propio del CUIT o global delegado — Fase 3.5) + WSFEv1
    try:
        auth = autenticar_wsaa_para_cuit(cuit_em, service="wsfe", ambiente=ambiente, cert_path=cert_path, key_path=key_path)
    except CertificadoPendienteError as exc:
        return {
            **borrador,
            "ok": False,
            "estado": "CERTIFICADO_PENDIENTE",
            "mensaje": str(exc),
        }
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

    asoc_block = ""
    if cbte_asoc and cbte_asoc.get("tipo") and cbte_asoc.get("nro"):
        asoc_block = f"""<ar:CbtesAsoc>
            <ar:CbteAsoc>
              <ar:Tipo>{int(cbte_asoc['tipo'])}</ar:Tipo>
              <ar:PtoVta>{int(cbte_asoc.get('pto_vta', pto_vta))}</ar:PtoVta>
              <ar:Nro>{int(cbte_asoc['nro'])}</ar:Nro>
            </ar:CbteAsoc>
          </ar:CbtesAsoc>"""

    cond_iva_block = f"<ar:CondicionIVAReceptorId>{int(cond_iva_id)}</ar:CondicionIVAReceptorId>" if cond_iva_id is not None else ""

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
                  {cond_iva_block}
                  {asoc_block}
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
    resultado = (root.findtext(".//ar:Resultado", default="", namespaces=ns) or "").strip()
    cae = (root.findtext(".//ar:CAE", default="", namespaces=ns) or "").strip()
    cae_vto = (root.findtext(".//ar:CAEFchVto", default="", namespaces=ns) or "").strip()
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

    if resultado == "A" and cae:
        res_label = "APROBADO"
    elif resultado == "R":
        res_label = "RECHAZADO"
    else:
        # N4-e: respuesta sin <Resultado> o ambigua se trata como INCIERTO, nunca RECHAZADO
        res_label = "INCIERTO"

    out_wsfe = {
        **borrador,
        "ok": bool(res_label == "APROBADO"),
        "fuente_certificado": auth.get("fuente_certificado", "global_delegado"),
        "cbte_nro": proximo,
        "resultado": res_label,
        "cae": cae,
        "cae_vencimiento": cae_vto,
        "qr_oficial_arca": qr_url,
        "observaciones": obs
    }
    if auth.get("alerta_vencimiento"):
        out_wsfe["alerta_vencimiento"] = auth["alerta_vencimiento"]
    if res_label == "INCIERTO":
        out_wsfe["estado"] = "ESTADO_INCIERTO_REQUIERE_REVISION"
        out_wsfe["incierto"] = True
    return out_wsfe


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


def parsear_respuesta_wsapoc(raw_xml: str, cuit_clean: str) -> Dict[str, Any]:
    """Parser estricto de GetPublicacionAPOCResponse (WSDL eapoc-ws / http://tempuri.org/).
    Ante XML malformado, Fault, <Errors> o código de error -> lanza WsapocResponseError (NUNCA 'no apócrifo')."""
    if not raw_xml or not raw_xml.strip():
        raise WsapocResponseError("Respuesta vacía de WSAPOC.")
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError as exc:
        raise WsapocResponseError(f"XML malformado en respuesta WSAPOC: {exc}") from exc

    # Detectar SOAP Fault o nodos <Errors>/<Err>
    for el in root.iter():
        tag_local = el.tag.split("}")[-1]
        if tag_local == "Fault":
            msg = "".join(el.itertext()).strip()[:240]
            raise WsapocResponseError(f"SOAP Fault en WSAPOC: {msg}")
        if tag_local in ("Errors", "ArrayOfError"):
            txt = " ".join(t.strip() for t in el.itertext() if t and t.strip())
            if txt:
                raise WsapocResponseError(f"WSAPOC informó errores: {txt[:240]}")

    result_el = None
    for el in root.iter():
        if el.tag.split("}")[-1] == "GetPublicacionAPOCResult":
            result_el = el
            break
    if result_el is None:
        raise WsapocResponseError("Respuesta WSAPOC sin nodo GetPublicacionAPOCResult.")

    codigo = None
    descripcion = ""
    publicaciones = []
    for ch in result_el:
        t = ch.tag.split("}")[-1]
        if t == "codigo":
            codigo = (ch.text or "").strip()
        elif t == "descripcion":
            descripcion = (ch.text or "").strip()
        elif t == "resultados":
            for pub in ch:
                if pub.tag.split("}")[-1] == "PublicacionAPOC":
                    item: Dict[str, str] = {}
                    for f in pub:
                        item[f.tag.split("}")[-1]] = (f.text or "").strip()
                    publicaciones.append(item)

    if codigo is not None and codigo.upper() not in ("", "0", "00", "200", "OK"):
        raise WsapocResponseError(f"WSAPOC devolvió código de error {codigo}: {descripcion or 'sin detalle'}")

    # W3: filtrar publicaciones estrictamente por PublicacionAPOC.Cuit == CUIT consultado
    publicaciones_cuit = [
        p for p in publicaciones
        if "".join(c for c in str(p.get("Cuit", "")) if c.isdigit()) == cuit_clean
    ]

    if publicaciones_cuit:
        first = publicaciones_cuit[0]
        return {
            "ok": True,
            "cuit": cuit_clean,
            "es_apocrifo": True,
            "fecha_condicion": first.get("FechaCondicion") or None,
            "fecha_publicacion": first.get("FechaPublicacion") or None,
            "descripcion": first.get("Descripcion") or descripcion or "Incluido en Base e-APOC",
            "publicaciones": publicaciones_cuit,
            "fuente": "WSAPOC",
        }

    return {
        "ok": True,
        "cuit": cuit_clean,
        "es_apocrifo": False,
        "fecha_condicion": None,
        "fuente": "WSAPOC",
    }


def consultar_apocrifo_wsapoc(
    cuit_consulta: str,
    ambiente: str = "produccion",
    cert_path: Optional[str] = None,
    key_path: Optional[str] = None,
    cuit_delegado: Optional[str] = None,
    usar_cache: bool = True,
) -> Dict[str, Any]:
    """Consulta Base e-APOC vía Web Service oficial WSAPOC (GetPublicacionAPOC) con caché de 24 h (Fase 3.3).
    - Sin certificado -> CertificadoPendienteError (el caller puede hacer fallback a Playwright).
    - Error de red/timeout/HTTP -> WsapocUnavailableError (fallback a Playwright).
    - XML malformado o <Errors> -> WsapocResponseError (error explícito, NUNCA 'no apócrifo')."""
    import time as _time
    cuit_clean = "".join(c for c in str(cuit_consulta or "") if c.isdigit())
    if len(cuit_clean) != 11:
        return {"ok": False, "cuit": cuit_clean, "error": "El CUIT del proveedor debe tener 11 dígitos.", "fuente": "WSAPOC"}

    env_key = "homologacion" if "homo" in (ambiente or "produccion").lower() else "produccion"
    cache_k = f"{env_key}:{cuit_clean}"
    if usar_cache:
        hit = _WSAPOC_CACHE.get(cache_k)
        if hit:
            if (_time.time() - hit[0]) < WSAPOC_CACHE_TTL_SEC:
                _WSAPOC_CACHE.move_to_end(cache_k)
                out_c = dict(hit[1])
                out_c["desde_cache"] = True
                return out_c
            _WSAPOC_CACHE.pop(cache_k, None)

    c_path = cert_path or os.environ.get("ARCA_WS_CERT")
    k_path = key_path or os.environ.get("ARCA_WS_KEY")
    if not c_path or not k_path:
        raise CertificadoPendienteError("Falta ARCA_WS_CERT / ARCA_WS_KEY para consultar WSAPOC.")

    try:
        auth = autenticar_wsaa(c_path, k_path, service="wsapoc", ambiente=env_key)
    except Exception as exc:
        raise WsapocUnavailableError(f"Error autenticando WSAA para wsapoc: {exc}") from exc

    cuit_del = "".join(c for c in str(cuit_delegado or os.environ.get("ARCA_WS_CUIT_DELEGADO") or "") if c.isdigit())
    del_block = f"<tem:CUITDelegado>{cuit_del}</tem:CUITDelegado>" if cuit_del else ""
    soap = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:tem="http://tempuri.org/">
   <soapenv:Header/>
   <soapenv:Body>
      <tem:GetPublicacionAPOC>
         <tem:Credencial>
            <tem:Token>{auth['token']}</tem:Token>
            <tem:Sign>{auth['sign']}</tem:Sign>
            {del_block}
         </tem:Credencial>
         <tem:cuit>{cuit_clean}</tem:cuit>
      </tem:GetPublicacionAPOC>
   </soapenv:Body>
</soapenv:Envelope>"""

    try:
        raw = _soap_post(
            ENDPOINTS[env_key]["wsapoc"],
            soap,
            soap_action="http://tempuri.org/Service/GetPublicacionAPOC",
            timeout=15,
        )
    except Exception as exc:
        raise WsapocUnavailableError(f"WSAPOC no disponible ({env_key}): {exc}") from exc

    res = parsear_respuesta_wsapoc(raw, cuit_clean)
    _WSAPOC_CACHE[cache_k] = (_time.time(), dict(res))
    _WSAPOC_CACHE.move_to_end(cache_k)
    while len(_WSAPOC_CACHE) > WSAPOC_CACHE_MAX_SIZE:
        _WSAPOC_CACHE.popitem(last=False)
    return res


if __name__ == "__main__":
    print("Probando conexión real FEDummy contra WSFEv1 Producción de ARCA...")
    print(json.dumps(verificar_estado_servidores_wsfe("produccion"), indent=2, ensure_ascii=False))
