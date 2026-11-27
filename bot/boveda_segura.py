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

def crear_token_usuario(email: str, label: str = "principal", custom_token: Optional[str] = None) -> Dict[str, Any]:
    """Crea un Personal Access Token (`imp_live_...` o frase clave personalizada >=16 chars) asociado a un email."""
    import re
    em = normalizar_email(email)
    if "@" not in em or "." not in em.split("@")[-1]:
        return {"ok": False, "error": "Email inválido."}

    ct = (custom_token or "").strip()
    if ct:
        if len(ct) < 16 or len(ct) > 128:
            return {"ok": False, "error": "La frase clave personalizada debe tener entre 16 y 128 caracteres."}
        if not re.fullmatch(r"[A-Za-z0-9._~-]+", ct):
            return {"ok": False, "error": "Usá solo letras, números y guiones/puntos/guion bajo (sin espacios ni símbolos de URL)."}
        if not (any(c.isalpha() for c in ct) and any(c.isdigit() for c in ct)):
            return {"ok": False, "error": "La frase clave personalizada debe combinar letras y números (ej: Cafe-Cordoba-Fiscal-8924)."}
        raw_token = ct
    else:
        raw_token = f"imp_live_{secrets.token_urlsafe(32)}"

    token_hash = _hash_token(raw_token)
    token_id = f"tok_{secrets.token_hex(6)}"
    ahora = _now_iso()

    with _vault_io_lock:
        acl = _load_acl()
        # Verificar unicidad global (nadie puede usar la misma frase clave de otro usuario)
        for other_em, other_u in acl["users"].items():
            for existing_tok in other_u.get("tokens", []):
                if secrets.compare_digest(existing_tok.get("hash", ""), token_hash):
                    if other_em != em:
                        return {"ok": False, "error": "Esa frase clave no está disponible. Elegí otra combinación."}
                    return {
                        "ok": True,
                        "email": em,
                        "token_id": existing_tok.get("id", token_id),
                        "token": raw_token,
                        "label": existing_tok.get("label", label),
                        "created_at": existing_tok.get("created_at", ahora),
                        "ya_existia": True,
                    }

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


# =====================================================================
# 4. BACKOFFICE DE PLATAFORMA (SUPER-ADMIN OWNER · GESTIÓN DESDE CUALQUIER LLM)
# =====================================================================

BILLING_FILE = VAULT_DIR / "admin_billing.enc"
PLANES_SAAS = {"free", "pro", "pyme", "estudio", "enterprise"}
ESTADOS_CUENTA = {"activo", "trial", "pausado", "suspendido"}


def obtener_admins_plataforma() -> set:
    raw = os.environ.get("PLATFORM_ADMIN_EMAILS", "damianbourdieu@gmail.com")
    return {normalizar_email(x) for x in raw.split(",") if normalizar_email(x)}


def es_admin_plataforma(email: Optional[str]) -> bool:
    em = normalizar_email(email or "")
    return bool(em and em in obtener_admins_plataforma())


def _load_billing() -> Dict[str, Any]:
    data = _read_enc_json(BILLING_FILE, {"subscriptions": {}, "invoices": []})
    data.setdefault("subscriptions", {})
    data.setdefault("invoices", [])
    return data


def _save_billing(data: Dict[str, Any]) -> None:
    _write_enc_json(BILLING_FILE, data)


def esta_usuario_suspendido(email: Optional[str]) -> bool:
    em = normalizar_email(email or "")
    if not em or es_admin_plataforma(em):
        return False
    with _vault_io_lock:
        b = _load_billing()
        sub = b["subscriptions"].get(em) or {}
        return sub.get("estado_cuenta") == "suspendido"


def admin_gestionar_suscripcion(
    admin_email: str,
    target_email: str,
    plan: str = "pro",
    estado_cuenta: str = "activo",
    precio_mensual_ars: float = 0.0,
    nota: str = "",
) -> Dict[str, Any]:
    if not es_admin_plataforma(admin_email):
        return {"ok": False, "acceso_denegado": True, "error": "Acción restringida al Super-Admin Owner de impuesto.com.ar."}
    em = normalizar_email(target_email)
    if "@" not in em:
        return {"ok": False, "error": "Email de cliente inválido."}
    pl = (plan or "pro").strip().lower()
    est = (estado_cuenta or "activo").strip().lower()
    if pl not in PLANES_SAAS:
        return {"ok": False, "error": f"Plan inválido '{plan}'. Usá: {sorted(PLANES_SAAS)}."}
    if est not in ESTADOS_CUENTA:
        return {"ok": False, "error": f"Estado inválido '{estado_cuenta}'. Usá: {sorted(ESTADOS_CUENTA)}."}

    ahora = _now_iso()
    with _vault_io_lock:
        b = _load_billing()
        prev = b["subscriptions"].get(em, {})
        b["subscriptions"][em] = {
            "email": em,
            "plan": pl,
            "estado_cuenta": est,
            "precio_mensual_ars": float(precio_mensual_ars or 0.0),
            "nota": (nota or "")[:300],
            "creado_at": prev.get("creado_at", ahora),
            "actualizado_at": ahora,
            "actualizado_por": normalizar_email(admin_email),
        }
        b["invoices"].append({
            "ts": ahora,
            "email": em,
            "plan": pl,
            "estado_cuenta": est,
            "precio_mensual_ars": float(precio_mensual_ars or 0.0),
            "nota": (nota or "")[:300],
            "admin": normalizar_email(admin_email),
        })
        b["invoices"] = b["invoices"][-500:]
        _save_billing(b)

    return {"ok": True, "suscripcion": b["subscriptions"][em]}


def admin_resumen_plataforma(admin_email: str) -> Dict[str, Any]:
    if not es_admin_plataforma(admin_email):
        return {"ok": False, "acceso_denegado": True, "error": "Acción restringida al Super-Admin Owner de impuesto.com.ar."}

    with _vault_io_lock:
        vault = _load_vault()
        acl = _load_acl()
        hist = _read_enc_json(HISTORY_FILE, [])
        billing = _load_billing()

    users = acl.get("users", {})
    cuit_acl = acl.get("cuit_acl", {})
    subs = billing.get("subscriptions", {})

    por_modo: Dict[str, int] = {}
    for rec in vault.values():
        m = rec.get("modo", "solo_lectura_cifrada")
        por_modo[m] = por_modo.get(m, 0) + 1

    por_llm: Dict[str, int] = {}
    for ev in hist:
        o = ev.get("origen_llm", "mcp")
        por_llm[o] = por_llm.get(o, 0) + 1

    por_plan: Dict[str, int] = {}
    mrr_ars = 0.0
    suspendidos = 0
    for em in set(users.keys()) | set(subs.keys()):
        s = subs.get(em, {"plan": "free", "estado_cuenta": "activo", "precio_mensual_ars": 0.0})
        pl = s.get("plan", "free")
        por_plan[pl] = por_plan.get(pl, 0) + 1
        if s.get("estado_cuenta") == "activo":
            mrr_ars += float(s.get("precio_mensual_ars") or 0.0)
        if s.get("estado_cuenta") == "suspendido":
            suspendidos += 1

    total_tokens = sum(len(u.get("tokens", [])) for u in users.values())
    total_invitados = sum(len(c.get("authorized", {})) for c in cuit_acl.values())

    return {
        "ok": True,
        "plataforma": "impuesto.com.ar",
        "admin": normalizar_email(admin_email),
        "kpis": {
            "usuarios_registrados": len(users),
            "cuits_vinculados": len(vault),
            "colaboradores_autorizados": total_invitados,
            "tokens_activos": total_tokens,
            "eventos_historial_totales": len(hist),
            "cuentas_suspendidas": suspendidos,
            "mrr_estimado_ars": round(mrr_ars, 2),
        },
        "distribucion_por_plan": por_plan,
        "distribucion_por_modo_cuit": por_modo,
        "actividad_por_llm": por_llm,
        "ultimos_5_eventos": list(reversed(hist[-5:])),
    }


def admin_listar_clientes(admin_email: str, filtro: str = "", plan: str = "", limite: int = 50) -> Dict[str, Any]:
    if not es_admin_plataforma(admin_email):
        return {"ok": False, "acceso_denegado": True, "error": "Acción restringida al Super-Admin Owner de impuesto.com.ar."}

    q = (filtro or "").strip().lower()
    plan_f = (plan or "").strip().lower()

    with _vault_io_lock:
        vault = _load_vault()
        acl = _load_acl()
        hist = _read_enc_json(HISTORY_FILE, [])
        billing = _load_billing()

    users = acl.get("users", {})
    cuit_acl = acl.get("cuit_acl", {})
    subs = billing.get("subscriptions", {})

    last_ev_by_email: Dict[str, str] = {}
    for ev in hist:
        em = ev.get("email", "")
        if em:
            last_ev_by_email[em] = ev.get("ts", "")

    clientes = []
    all_emails = sorted(set(users.keys()) | set(subs.keys()) | {c.get("owner_email") for c in cuit_acl.values() if c.get("owner_email")})
    for em in all_emails:
        u = users.get(em, {})
        sub = subs.get(em, {"plan": "free", "estado_cuenta": "activo", "precio_mensual_ars": 0.0, "nota": ""})
        cuits_propios = [
            {
                "cuit": c,
                "modo": (vault.get(c) or {}).get("modo", "solo_lectura_cifrada"),
                "invitados": list((info.get("authorized") or {}).keys()),
            }
            for c, info in cuit_acl.items()
            if info.get("owner_email") == em
        ]
        if plan_f and sub.get("plan", "free") != plan_f:
            continue
        if q:
            haystack = f"{em} {sub.get('plan','')} {sub.get('nota','')} " + " ".join(x["cuit"] for x in cuits_propios)
            if q not in haystack.lower():
                continue
        clientes.append({
            "email": em,
            "plan": sub.get("plan", "free"),
            "estado_cuenta": sub.get("estado_cuenta", "activo"),
            "precio_mensual_ars": sub.get("precio_mensual_ars", 0.0),
            "tokens_activos": len(u.get("tokens", [])),
            "cuits_propios": cuits_propios,
            "ultima_actividad": last_ev_by_email.get(em),
            "creado_at": u.get("created_at") or sub.get("creado_at"),
            "nota": sub.get("nota", ""),
        })

    lim = max(1, min(int(limite or 50), 200))
    return {
        "ok": True,
        "total_encontrados": len(clientes),
        "clientes": clientes[:lim],
    }


def admin_ver_movimientos(
    admin_email: str,
    email: str = "",
    cuit: str = "",
    origen_llm: str = "",
    limite: int = 50,
) -> Dict[str, Any]:
    if not es_admin_plataforma(admin_email):
        return {"ok": False, "acceso_denegado": True, "error": "Acción restringida al Super-Admin Owner de impuesto.com.ar."}

    em_f = normalizar_email(email)
    cuit_f = normalizar_cuit(cuit)
    llm_f = (origen_llm or "").strip().lower()

    with _vault_io_lock:
        hist = _read_enc_json(HISTORY_FILE, [])

    out = []
    for ev in reversed(hist):
        if em_f and ev.get("email") != em_f:
            continue
        if cuit_f and ev.get("cuit") != cuit_f:
            continue
        if llm_f and ev.get("origen_llm") != llm_f:
            continue
        out.append(ev)
        if len(out) >= max(1, min(int(limite or 50), 200)):
            break

    return {"ok": True, "total_eventos": len(out), "movimientos": out}


# =====================================================================
# 5. LOGIN UNIVERSAL POR CÓDIGO DE 6 DÍGITOS (OTP EMAIL — 100% MAILS)
# =====================================================================

_otp_lock = threading.Lock()
_otp_store: Dict[str, Dict[str, Any]] = {}
OTP_TTL_SEC = 600  # 10 minutos


def _enviar_email_otp(destinatario: str, codigo: str) -> Tuple[bool, str]:
    """Envía el código OTP de 6 dígitos usando Resend API o SMTP si están configurados."""
    import urllib.request
    import smtplib
    from email.message import EmailMessage

    from_addr = os.environ.get("MAIL_FROM", "impuesto.com.ar <hola@impuesto.com.ar>")
    subject = f"Tu código de acceso a impuesto.com.ar: {codigo}"
    body_txt = (
        f"Tu código de acceso único (válido por 10 minutos) es: {codigo}\n\n"
        "Ingresalo directamente en tu chat de ChatGPT, Claude, Gemini o Copilot.\n"
        "Si no solicitaste este código, ignorá este correo."
    )
    body_html = (
        f"<div style='font-family:system-ui,sans-serif;max-width:480px;padding:24px'>"
        f"<h2 style='color:#0B6E4F;margin:0 0 12px'>Tu código de acceso a impuesto.com.ar</h2>"
        f"<p style='font-size:15px;color:#334155'>Ingresá este código de 6 dígitos en tu chat (vence en 10 minutos):</p>"
        f"<div style='font-size:34px;font-weight:800;letter-spacing:6px;background:#F0FDF4;border:1px solid #BBF7D0;border-radius:12px;padding:16px;text-align:center;color:#074F39;margin:16px 0'>{codigo}</div>"
        f"<p style='font-size:13px;color:#64748B'>Funciona con cualquier asistente (ChatGPT, Claude, Gemini, Copilot, Cursor). Si no lo pediste, ignorá este mensaje.</p></div>"
    )

    resend_key = os.environ.get("RESEND_API_KEY", "").strip()
    if resend_key:
        try:
            payload = json.dumps({
                "from": from_addr,
                "to": [destinatario],
                "subject": subject,
                "text": body_txt,
                "html": body_html,
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.resend.com/emails",
                data=payload,
                headers={
                    "Authorization": f"Bearer {resend_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "impuesto-com-ar/3.1",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if 200 <= resp.status < 300:
                    return True, "resend"
            return False, "Resend devolvió un error al enviar el correo."
        except Exception as e:
            return False, f"Error enviando correo vía Resend: {e}"

    smtp_host = os.environ.get("SMTP_HOST", "").strip()
    smtp_user = os.environ.get("SMTP_USER", "").strip()
    smtp_pass = os.environ.get("SMTP_PASS", "").strip()
    if smtp_host and smtp_user and smtp_pass:
        try:
            smtp_port = int(os.environ.get("SMTP_PORT", "587"))
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = from_addr
            msg["To"] = destinatario
            msg.set_content(body_txt)
            msg.add_alternative(body_html, subtype="html")
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as s:
                s.starttls()
                s.login(smtp_user, smtp_pass)
                s.send_message(msg)
            return True, "smtp"
        except Exception as e:
            return False, f"Error enviando correo vía SMTP: {e}"

    return False, "SIN_PROVEEDOR_EMAIL"


def solicitar_codigo_otp_email(email: str) -> Dict[str, Any]:
    """Genera un código OTP de 6 dígitos (SHA-256 en memoria, TTL 10 min) y lo envía por email."""
    em = normalizar_email(email)
    if "@" not in em or "." not in em.split("@")[-1]:
        return {"ok": False, "error": "Email inválido."}

    codigo = f"{secrets.randbelow(900000) + 100000}"
    exp = datetime.datetime.now(datetime.timezone.utc).timestamp() + OTP_TTL_SEC

    with _otp_lock:
        _otp_store[em] = {"hash": _hash_token(codigo), "exp": exp, "intentos": 0}

    enviado, proveedor = _enviar_email_otp(em, codigo)
    if not enviado:
        if proveedor == "SIN_PROVEEDOR_EMAIL":
            return {
                "ok": False,
                "envio_email_configurado": False,
                "email": em,
                "mensaje": (
                    "El envío automático de códigos por email aún no tiene un proveedor SMTP/Resend configurado en el servidor "
                    "(falta configurar RESEND_API_KEY o SMTP_HOST/SMTP_USER/SMTP_PASS). "
                    "Mientras tanto, iniciá sesión en el chat con tu frase clave (`iniciar_sesion_en_chat`) o vinculá tu cuenta (`vincular_cuenta_en_chat`)."
                ),
            }
        return {"ok": False, "envio_email_configurado": True, "error": proveedor}

    return {
        "ok": True,
        "envio_email_configurado": True,
        "proveedor": proveedor,
        "email": em,
        "vence_en_minutos": 10,
        "mensaje": f"Te enviamos un código de 6 dígitos a {em} (válido por 10 minutos). Escribilo acá mismo en el chat para entrar.",
    }


def verificar_codigo_otp_email(email: str, codigo: str, origen_llm: str = "mcp") -> Dict[str, Any]:
    """Verifica el código OTP de 6 dígitos (uso único, máx 5 intentos) y emite un token_sesion válido."""
    em = normalizar_email(email)
    cod = "".join(ch for ch in str(codigo or "") if ch.isdigit())
    if "@" not in em or len(cod) != 6:
        return {"ok": False, "acceso_denegado": True, "error": "Indicá tu email y el código numérico de 6 dígitos."}

    now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
    with _otp_lock:
        rec = _otp_store.get(em)
        if not rec:
            return {"ok": False, "acceso_denegado": True, "error": "No hay un código activo para ese email. Pedí uno nuevo."}
        if now_ts > rec["exp"]:
            _otp_store.pop(em, None)
            return {"ok": False, "acceso_denegado": True, "error": "El código venció (superó los 10 minutos). Pedí uno nuevo."}
        rec["intentos"] += 1
        if rec["intentos"] > 5:
            _otp_store.pop(em, None)
            return {"ok": False, "acceso_denegado": True, "error": "Demasiados intentos fallidos. Pedí un código nuevo."}
        if not secrets.compare_digest(rec["hash"], _hash_token(cod)):
            return {"ok": False, "acceso_denegado": True, "error": "Código incorrecto. Verificá los 6 dígitos en tu correo."}
        # Uso único: consumir el OTP
        _otp_store.pop(em, None)

    tok = crear_token_usuario(email=em, label=f"otp_{origen_llm}")
    if not tok.get("ok"):
        return tok
    cuits = listar_cuits_autorizados(em)
    return {
        "ok": True,
        "usuario": em,
        "es_owner_plataforma": es_admin_plataforma(em),
        "token_sesion": tok["token"],
        "empresas_vinculadas": cuits,
        "mensaje": f"¡Listo! Sesión iniciada como {em} ({len(cuits)} CUIT(s) autorizados).",
        "instruccion_para_ia": (
            "Pasá este `token_sesion` en todas las herramientas que llames en este chat (NO muestres el token al usuario). "
            "Si ya tiene CUITs vinculados, avanzá directo; si aún no tiene, pedile CUIT + Clave Fiscal con `vincular_cuenta_en_chat`."
        ),
    }
