"""
bot/boveda_segura.py
Bóveda Cifrada (AES-256 / Fernet) para credenciales ARCA y Certificados Digitales WSAA.

Principios de seguridad:
- Las claves fiscales y claves privadas .key NUNCA se guardan en texto plano ni se loguean.
- Cifrado en reposo con Fernet (AES-128-CBC + HMAC-SHA256) usando IMPUESTO_VAULT_KEY.
- Permite vinculación en modo SOLO LECTURA o mediante Delegación / Certificado WSAA.
- El usuario puede revocar el acceso en 1 clic desde /vincular o desde ARCA.
"""

import os
import json
import base64
import hashlib
import datetime
from pathlib import Path
from typing import Dict, Any, Optional

try:
    from cryptography.fernet import Fernet
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

ROOT = Path(__file__).resolve().parent.parent
VAULT_DIR = ROOT / "data" / "boveda"
VAULT_FILE = VAULT_DIR / "credenciales.enc"
KEY_FILE = VAULT_DIR / ".vault_key"


def _get_fernet() -> "Fernet":
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    env_key = os.environ.get("IMPUESTO_VAULT_KEY", "").strip()
    if env_key:
        raw = hashlib.sha256(env_key.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(raw)
    elif KEY_FILE.exists():
        key = KEY_FILE.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        KEY_FILE.write_bytes(key)
        os.chmod(KEY_FILE, 0o600)
    return Fernet(key)


def _load_vault() -> Dict[str, Any]:
    if not VAULT_FILE.exists():
        return {}
    if not HAS_CRYPTO:
        raise RuntimeError("Falta librería 'cryptography' para operar la bóveda cifrada.")
    f = _get_fernet()
    data = f.decrypt(VAULT_FILE.read_bytes())
    return json.loads(data.decode("utf-8"))


def _save_vault(vault: Dict[str, Any]) -> None:
    if not HAS_CRYPTO:
        raise RuntimeError("Falta librería 'cryptography' para operar la bóveda cifrada.")
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    f = _get_fernet()
    token = f.encrypt(json.dumps(vault, ensure_ascii=False).encode("utf-8"))
    VAULT_FILE.write_bytes(token)
    os.chmod(VAULT_FILE, 0o600)


def normalizar_cuit(cuit: str) -> str:
    return "".join(ch for ch in (cuit or "") if ch.isdigit())


def guardar_credenciales_cifradas(
    cuit: str,
    clave_fiscal: Optional[str] = None,
    modo: str = "solo_lectura_cifrada",
    cert_pem: Optional[str] = None,
    key_pem: Optional[str] = None,
    alias: str = ""
) -> Dict[str, Any]:
    cuit_clean = normalizar_cuit(cuit)
    if len(cuit_clean) != 11:
        return {"ok": False, "error": "CUIT inválido (debe tener 11 dígitos)."}

    vault = _load_vault()
    ahora = datetime.datetime.now(datetime.timezone.utc).isoformat()
    vault[cuit_clean] = {
        "cuit": cuit_clean,
        "modo": modo,
        "alias": alias or f"Contribuyente {cuit_clean}",
        "clave_fiscal": clave_fiscal or "",
        "tiene_wsaa": bool(cert_pem and key_pem),
        "cert_pem": cert_pem or "",
        "key_pem": key_pem or "",
        "solo_lectura_por_defecto": True,
        "vinculado_at": ahora,
    }
    _save_vault(vault)
    return {
        "ok": True,
        "cuit": cuit_clean,
        "modo": modo,
        "cifrado": "Fernet AES + HMAC-SHA256",
        "solo_lectura_por_defecto": True,
        "vinculado_at": ahora,
    }


def obtener_credenciales_descifradas(cuit: str) -> Optional[Dict[str, Any]]:
    cuit_clean = normalizar_cuit(cuit)
    vault = _load_vault()
    return vault.get(cuit_clean)


def estado_vinculacion(cuit: str) -> Dict[str, Any]:
    cuit_clean = normalizar_cuit(cuit)
    vault = _load_vault()
    rec = vault.get(cuit_clean)
    if not rec:
        return {
            "vinculado": False,
            "cuit": cuit_clean,
            "mensaje": "Este CUIT aún no está vinculado a la bóveda segura de impuesto.com.ar."
        }
    return {
        "vinculado": True,
        "cuit": cuit_clean,
        "modo": rec.get("modo"),
        "tiene_wsaa": rec.get("tiene_wsaa", False),
        "solo_lectura_por_defecto": rec.get("solo_lectura_por_defecto", True),
        "vinculado_at": rec.get("vinculado_at"),
    }


def revocar_credenciales(cuit: str) -> Dict[str, Any]:
    cuit_clean = normalizar_cuit(cuit)
    vault = _load_vault()
    existed = cuit_clean in vault
    if existed:
        vault.pop(cuit_clean, None)
        _save_vault(vault)
    return {"ok": True, "cuit": cuit_clean, "revocado": existed}
