"""
bot/boveda_segura.py
Bóveda Cifrada Multi-Tenant (AES-256 / Fernet) para credenciales ARCA,
Control de Acceso por Email (Owner / Editor / Solo Lectura) e Historial Compartido Cross-LLM.

Principios de seguridad:
- Las claves fiscales y claves privadas .key NUNCA se guardan en texto plano ni se loguean.
- Cifrado en reposo con Fernet (AES-128-CBC + HMAC-SHA256) usando IMPUESTO_VAULT_KEY.
- Aislamiento estricto por dueño (owner_email) y tokens personales (SHA-256 en reposo, estilo GitHub PAT).
- Ningún usuario puede consultar ni listar un CUIT que no le pertenece o no le fue autorizado explícitamente.
- Historial unificado cifrado para continuar trabajo entre Claude, ChatGPT, Gemini, Copilot y Cursor.
"""

import os
import json
import base64
import hashlib
import secrets
import datetime
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

try:
    from cryptography.fernet import Fernet
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

ROOT = Path(__file__).resolve().parent.parent
VAULT_DIR = ROOT / "data" / "boveda"
VAULT_FILE = VAULT_DIR / "credenciales.enc"
ACL_FILE = VAULT_DIR / "acl.enc"
HISTORY_FILE = VAULT_DIR / "historial.enc"
KEY_FILE = VAULT_DIR / ".vault_key"

_vault_io_lock = threading.Lock()
ROLES_VALIDOS = {"solo_lectura", "editor", "owner"}
MAX_HISTORY_EVENTS = 1000


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


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


def _read_enc_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    if not HAS_CRYPTO:
        raise RuntimeError("Falta librería 'cryptography' para operar la bóveda cifrada.")
    f = _get_fernet()
    data = f.decrypt(path.read_bytes())
    return json.loads(data.decode("utf-8"))


def _write_enc_json(path: Path, obj: Any) -> None:
    if not HAS_CRYPTO:
        raise RuntimeError("Falta librería 'cryptography' para operar la bóveda cifrada.")
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    f = _get_fernet()
    token = f.encrypt(json.dumps(obj, ensure_ascii=False).encode("utf-8"))
    path.write_bytes(token)
    os.chmod(path, 0o600)


def _load_vault() -> Dict[str, Any]:
    return _read_enc_json(VAULT_FILE, {})


def _save_vault(vault: Dict[str, Any]) -> None:
    _write_enc_json(VAULT_FILE, vault)


def _load_acl() -> Dict[str, Any]:
    acl = _read_enc_json(ACL_FILE, {"users": {}, "cuit_acl": {}})
    acl.setdefault("users", {})
    acl.setdefault("cuit_acl", {})
    return acl


def _save_acl(acl: Dict[str, Any]) -> None:
    _write_enc_json(ACL_FILE, acl)


def normalizar_cuit(cuit: str) -> str:
    return "".join(ch for ch in (cuit or "") if ch.isdigit())


def normalizar_email(email: str) -> str:
    return (email or "").strip().lower()


def _hash_token(token: str) -> str:
    return hashlib.sha256((token or "").strip().encode("utf-8")).hexdigest()


# =====================================================================
# 1. IDENTIDAD MULTI-LLM (TOKENS PERSONALES TIPO GITHUB PAT)
# =====================================================================

def crear_token_usuario(email: str, label: str = "principal") -> Dict[str, Any]:
    """Crea un Personal Access Token (`imp_live_...`) asociado a un email. El secreto solo se muestra una vez."""
    em = normalizar_email(email)
    if "@" not in em or "." not in em.split("@")[-1]:
        return {"ok": False, "error": "Email inválido."}

    raw_token = f"imp_live_{secrets.token_urlsafe(32)}"
    token_hash = _hash_token(raw_token)
    token_id = f"tok_{secrets.token_hex(6)}"
    ahora = _now_iso()

    with _vault_io_lock:
        acl = _load_acl()
        user = acl["users"].setdefault(em, {"email": em, "created_at": ahora, "tokens": []})
        user["tokens"].append({
            "id": token_id,
            "hash": token_hash,
            "label": (label or "principal")[:40],
            "created_at": ahora,
        })
        # Limitar a últimos 20 tokens activos por usuario
        user["tokens"] = user["tokens"][-20:]
        _save_acl(acl)

    return {
        "ok": True,
        "email": em,
        "token_id": token_id,
        "token": raw_token,
        "label": label,
        "created_at": ahora,
    }


def resolver_email_por_token(token: Optional[str]) -> Optional[str]:
    """Valida un Personal Access Token y devuelve el email autenticado (o None si es inválido)."""
    t = (token or "").strip()
    if not t:
        return None
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    if not t:
        return None
    target_hash = _hash_token(t)
    with _vault_io_lock:
        acl = _load_acl()
        for em, u in acl["users"].items():
            for tok in u.get("tokens", []):
                if secrets.compare_digest(tok.get("hash", ""), target_hash):
                    return em
    return None


def revocar_tokens_usuario(email: str, token_id: Optional[str] = None) -> Dict[str, Any]:
    em = normalizar_email(email)
    with _vault_io_lock:
        acl = _load_acl()
        u = acl["users"].get(em)
        if not u:
            return {"ok": False, "error": "Usuario no encontrado."}
        if token_id:
            before = len(u.get("tokens", []))
            u["tokens"] = [t for t in u.get("tokens", []) if t.get("id") != token_id]
            removed = before - len(u["tokens"])
        else:
            removed = len(u.get("tokens", []))
            u["tokens"] = []
        _save_acl(acl)
    return {"ok": True, "email": em, "tokens_revocados": removed}


# =====================================================================
# 2. BÓVEDA DE CREDENCIALES ARCA + CONTROL DE ACCESO POR CUIT (ACL)
# =====================================================================

def asignar_owner_cuit(cuit: str, owner_email: str) -> Dict[str, Any]:
    cuit_clean = normalizar_cuit(cuit)
    em = normalizar_email(owner_email)
    if len(cuit_clean) != 11 or "@" not in em:
        return {"ok": False, "error": "CUIT (11 dígitos) o email inválido."}
    ahora = _now_iso()
    with _vault_io_lock:
        acl = _load_acl()
        entry = acl["cuit_acl"].setdefault(cuit_clean, {"owner_email": em, "authorized": {}, "created_at": ahora})
        entry["owner_email"] = em
        entry["updated_at"] = ahora
        _save_acl(acl)
    return {"ok": True, "cuit": cuit_clean, "owner_email": em}


def guardar_credenciales_cifradas(
    cuit: str,
    clave_fiscal: Optional[str] = None,
    modo: str = "solo_lectura_cifrada",
    cert_pem: Optional[str] = None,
    key_pem: Optional[str] = None,
    alias: str = "",
    owner_email: Optional[str] = None,
) -> Dict[str, Any]:
    cuit_clean = normalizar_cuit(cuit)
    if len(cuit_clean) != 11:
        return {"ok": False, "error": "CUIT inválido (debe tener 11 dígitos)."}

    em = normalizar_email(owner_email or "")
    ahora = _now_iso()

    with _vault_io_lock:
        vault = _load_vault()
        acl = _load_acl()

        # Si el CUIT ya tiene dueño distinto, impedir que otro lo secuestre sin autorización
        existing_acl = acl["cuit_acl"].get(cuit_clean)
        if existing_acl and existing_acl.get("owner_email") and em and existing_acl["owner_email"] != em:
            return {
                "ok": False,
                "error": (
                    f"El CUIT {cuit_clean} ya tiene un propietario registrado. "
                    "Pedile al Owner que te autorice por email desde su chat (`autorizar_usuario_cuit`)."
                ),
            }

        vault[cuit_clean] = {
            "cuit": cuit_clean,
            "modo": modo,
            "alias": alias or f"Contribuyente {cuit_clean}",
            "clave_fiscal": clave_fiscal or "",
            "tiene_wsaa": bool(cert_pem and key_pem),
            "cert_pem": cert_pem or "",
            "key_pem": key_pem or "",
            "solo_lectura_por_defecto": True,
            "owner_email": em or (existing_acl or {}).get("owner_email", ""),
            "vinculado_at": ahora,
        }
        _save_vault(vault)

        if em:
            entry = acl["cuit_acl"].setdefault(cuit_clean, {"owner_email": em, "authorized": {}, "created_at": ahora})
            if not entry.get("owner_email"):
                entry["owner_email"] = em
            entry["updated_at"] = ahora
            _save_acl(acl)

    return {
        "ok": True,
        "cuit": cuit_clean,
        "owner_email": em or None,
        "modo": modo,
        "cifrado": "Fernet AES + HMAC-SHA256",
        "solo_lectura_por_defecto": True,
        "vinculado_at": ahora,
    }


def obtener_credenciales_descifradas(cuit: str) -> Optional[Dict[str, Any]]:
    cuit_clean = normalizar_cuit(cuit)
    with _vault_io_lock:
        vault = _load_vault()
        return vault.get(cuit_clean)


def verificar_permiso_cuit(email: Optional[str], cuit: str, nivel: str = "lectura") -> Tuple[bool, Optional[str], str]:
    """
    Verifica si `email` tiene permiso sobre `cuit` para el `nivel` solicitado:
      - 'lectura': owner, editor o solo_lectura
      - 'escritura': owner o editor
      - 'owner': solo owner
    """
    em = normalizar_email(email or "")
    cuit_clean = normalizar_cuit(cuit)
    if not em:
        return False, None, "Sesión no autenticada. Conectá tu token personal o iniciá sesión en https://impuesto.com.ar/vincular."
    if len(cuit_clean) != 11:
        return False, None, "CUIT inválido (debe tener 11 dígitos)."

    with _vault_io_lock:
        acl = _load_acl()
        entry = acl["cuit_acl"].get(cuit_clean)
        if not entry:
            return False, None, f"El CUIT {cuit_clean} no está vinculado a tu cuenta."

        role = None
        if entry.get("owner_email") == em:
            role = "owner"
        else:
            inv = (entry.get("authorized") or {}).get(em)
            if inv:
                role = inv.get("role", "solo_lectura")

        if not role:
            return False, None, f"Acceso denegado: tu cuenta ({em}) no está autorizada para operar el CUIT {cuit_clean}."

        if nivel == "owner" and role != "owner":
            return False, role, f"Acción restringida al propietario (Owner) del CUIT {cuit_clean}. Tu rol actual es '{role}'."
        if nivel == "escritura" and role not in ("owner", "editor"):
            return False, role, f"Tu rol sobre el CUIT {cuit_clean} es 'solo_lectura' y no permite escrituras/emisiones."
        return True, role, "ok"


def autorizar_usuario_cuit(owner_email: str, cuit: str, email_invitado: str, rol: str = "solo_lectura") -> Dict[str, Any]:
    cuit_clean = normalizar_cuit(cuit)
    em_owner = normalizar_email(owner_email)
    em_inv = normalizar_email(email_invitado)
    rol_clean = (rol or "solo_lectura").strip().lower()
    if rol_clean not in ROLES_VALIDOS:
        return {"ok": False, "error": f"Rol inválido '{rol}'. Usá: solo_lectura, editor o owner."}
    if "@" not in em_inv:
        return {"ok": False, "error": "Email del usuario a autorizar inválido."}

    ok, _, reason = verificar_permiso_cuit(em_owner, cuit_clean, nivel="owner")
    if not ok:
        return {"ok": False, "acceso_denegado": True, "error": reason}

    ahora = _now_iso()
    with _vault_io_lock:
        acl = _load_acl()
        entry = acl["cuit_acl"][cuit_clean]
        entry.setdefault("authorized", {})[em_inv] = {
            "role": rol_clean,
            "granted_by": em_owner,
            "granted_at": ahora,
        }
        entry["updated_at"] = ahora
        _save_acl(acl)

    return {
        "ok": True,
        "cuit": cuit_clean,
        "email_autorizado": em_inv,
        "rol": rol_clean,
        "autorizado_por": em_owner,
        "mensaje": (
            f"Listo: {em_inv} quedó autorizado con rol '{rol_clean}' sobre el CUIT {cuit_clean}. "
            "Cuando se conecte desde su propio Claude/ChatGPT/Gemini con su email (generando su token en https://impuesto.com.ar/vincular), "
            "verá este CUIT automáticamente sin conocer nunca tu Clave Fiscal."
        ),
    }


def revocar_usuario_cuit(owner_email: str, cuit: str, email_invitado: str) -> Dict[str, Any]:
    cuit_clean = normalizar_cuit(cuit)
    em_owner = normalizar_email(owner_email)
    em_inv = normalizar_email(email_invitado)
    ok, _, reason = verificar_permiso_cuit(em_owner, cuit_clean, nivel="owner")
    if not ok:
        return {"ok": False, "acceso_denegado": True, "error": reason}

    with _vault_io_lock:
        acl = _load_acl()
        auth_map = acl["cuit_acl"][cuit_clean].setdefault("authorized", {})
        existed = em_inv in auth_map
        auth_map.pop(em_inv, None)
        _save_acl(acl)

    return {
        "ok": True,
        "cuit": cuit_clean,
        "email_revocado": em_inv,
        "estaba_autorizado": existed,
        "mensaje": f"Acceso revocado al instante para {em_inv} en el CUIT {cuit_clean}." if existed else f"{em_inv} no tenía acceso previo al CUIT {cuit_clean}.",
    }


def listar_accesos_cuit(actor_email: str, cuit: str) -> Dict[str, Any]:
    cuit_clean = normalizar_cuit(cuit)
    ok, role, reason = verificar_permiso_cuit(actor_email, cuit_clean, nivel="lectura")
    if not ok:
        return {"ok": False, "acceso_denegado": True, "error": reason}

    with _vault_io_lock:
        acl = _load_acl()
        entry = acl["cuit_acl"].get(cuit_clean, {})
        invitados = [
            {"email": em, "rol": info.get("role"), "autorizado_por": info.get("granted_by"), "fecha": info.get("granted_at")}
            for em, info in (entry.get("authorized") or {}).items()
        ]
    return {
        "ok": True,
        "cuit": cuit_clean,
        "tu_rol": role,
        "owner_email": entry.get("owner_email"),
        "usuarios_autorizados": invitados,
    }


def listar_cuits_autorizados(actor_email: str) -> List[Dict[str, Any]]:
    """Lista SOLO los CUITs donde `actor_email` es Owner o fue autorizado explícitamente."""
    em = normalizar_email(actor_email)
    if not em:
        return []
    with _vault_io_lock:
        vault = _load_vault()
        acl = _load_acl()
        out = []
        for cuit_clean, entry in acl["cuit_acl"].items():
            role = None
            if entry.get("owner_email") == em:
                role = "owner"
            elif em in (entry.get("authorized") or {}):
                role = entry["authorized"][em].get("role", "solo_lectura")
            if not role:
                continue
            rec = vault.get(cuit_clean, {})
            out.append({
                "cuit": cuit_clean,
                "rol": role,
                "owner_email": entry.get("owner_email"),
                "alias": rec.get("alias") or f"Contribuyente {cuit_clean}",
                "modo": rec.get("modo", "solo_lectura_cifrada"),
                "solo_lectura_por_defecto": rec.get("solo_lectura_por_defecto", True),
                "tiene_wsaa": rec.get("tiene_wsaa", False),
                "vinculado_at": rec.get("vinculado_at"),
            })
        return out


def estado_vinculacion(cuit: str) -> Dict[str, Any]:
    cuit_clean = normalizar_cuit(cuit)
    with _vault_io_lock:
        vault = _load_vault()
        rec = vault.get(cuit_clean)
    if not rec:
        return {
            "vinculado": False,
            "cuit": cuit_clean,
            "mensaje": "Este CUIT aún no está vinculado a la bóveda segura de impuesto.com.ar.",
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
    with _vault_io_lock:
        vault = _load_vault()
        existed = cuit_clean in vault
        if existed:
            vault.pop(cuit_clean, None)
            _save_vault(vault)
    return {"ok": True, "cuit": cuit_clean, "revocado": existed}


def listar_cuits_vinculados() -> list:
    """Uso administrativo interno (NO exponer sin autenticar). Para usuarios usar `listar_cuits_autorizados`."""
    with _vault_io_lock:
        vault = _load_vault()
    return [
        {
            "cuit": cuit_clean,
            "alias": rec.get("alias") or f"Contribuyente {cuit_clean}",
            "modo": rec.get("modo", "solo_lectura_cifrada"),
            "solo_lectura_por_defecto": rec.get("solo_lectura_por_defecto", True),
            "tiene_wsaa": rec.get("tiene_wsaa", False),
            "vinculado_at": rec.get("vinculado_at"),
        }
        for cuit_clean, rec in vault.items()
    ]


# =====================================================================
# 3. HISTORIAL COMPARTIDO CROSS-LLM (ESTILO GITHUB ACTIVITY LOG)
# =====================================================================

def registrar_evento_historial(
    email: str,
    cuit: str,
    origen_llm: str,
    accion: str,
    titulo: str,
    detalle: str = "",
) -> Dict[str, Any]:
    """Guarda un evento en la línea de tiempo cifrada compartida entre Claude, ChatGPT, Gemini, Copilot y Cursor."""
    ev = {
        "id": f"ev_{secrets.token_hex(6)}",
        "ts": _now_iso(),
        "email": normalizar_email(email),
        "cuit": normalizar_cuit(cuit),
        "origen_llm": (origen_llm or "mcp").lower(),
        "accion": accion,
        "titulo": (titulo or "")[:160],
        "detalle": (detalle or "")[:1200],
    }
    with _vault_io_lock:
        hist = _read_enc_json(HISTORY_FILE, [])
        hist.append(ev)
        hist = hist[-MAX_HISTORY_EVENTS:]
        _write_enc_json(HISTORY_FILE, hist)
    return ev


def obtener_historial_actividad(actor_email: str, cuit: str = "", limite: int = 25) -> Dict[str, Any]:
    """Devuelve el historial compartido cross-LLM filtrado estrictamente a los CUITs autorizados del usuario."""
    em = normalizar_email(actor_email)
    if not em:
        return {"ok": False, "acceso_denegado": True, "error": "Sesión no autenticada."}

    cuit_filter = normalizar_cuit(cuit)
    autorizados = {item["cuit"] for item in listar_cuits_autorizados(em)}
    if cuit_filter and cuit_filter not in autorizados:
        return {"ok": False, "acceso_denegado": True, "error": f"No tenés permiso para ver el historial del CUIT {cuit_filter}."}

    with _vault_io_lock:
        hist = _read_enc_json(HISTORY_FILE, [])

    filtrados = []
    for ev in reversed(hist):
        ev_cuit = ev.get("cuit", "")
        if cuit_filter:
            if ev_cuit != cuit_filter:
                continue
        else:
            if ev_cuit and ev_cuit not in autorizados:
                continue
            if not ev_cuit and ev.get("email") != em:
                continue
        filtrados.append(ev)
        if len(filtrados) >= max(1, min(int(limite or 25), 100)):
            break

    return {
        "ok": True,
        "usuario": em,
        "cuit_filtrado": cuit_filter or "todos_mis_cuits",
        "total_eventos": len(filtrados),
        "eventos": filtrados,
    }
