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
import time
import base64
import hashlib
import secrets
import datetime
import threading
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger("boveda_segura")

import logging
try:
    from cryptography.fernet import Fernet, InvalidToken
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False
    InvalidToken = Exception

logger_boveda = logging.getLogger("impuesto.boveda")


class VaultKeyMismatchError(RuntimeError):
    """O2: la clave de bóveda configurada no coincide con la usada para cifrar el archivo .enc."""

ROOT = Path(__file__).resolve().parent.parent
VAULT_DIR = ROOT / "data" / "boveda"
VAULT_FILE = VAULT_DIR / "credenciales.enc"
ACL_FILE = VAULT_DIR / "acl.enc"
HISTORY_FILE = VAULT_DIR / "historial.enc"
KEY_FILE = VAULT_DIR / ".vault_key"

_vault_io_lock = threading.Lock()
ROLES_VALIDOS = {"solo_lectura", "editor", "owner"}
MAX_HISTORY_EVENTS = 1000
PENDING_TTL_SEC = int(os.environ.get("PENDING_CUIT_TTL_SEC", "1800"))  # 30 minutos: CUITs pendientes sin login exitoso expiran (N1-b / N1-i)


def hash_clave_cuit(cuit: str, clave: str) -> str:
    """Hash determinístico SHA-256 de (cuit, clave) para vincular logins exitosos/fallidos sin guardar texto plano."""
    return hashlib.sha256(f"{normalizar_cuit(cuit)}:{(clave or '').strip()}".encode("utf-8")).hexdigest()


def _es_pendiente_vencido(entry: Dict[str, Any], now_ts: Optional[float] = None) -> bool:
    """True si la entrada ACL está pendiente de validación hace >= PENDING_TTL_SEC desde created_at (N1-b / N1-i)."""
    if not isinstance(entry, dict) or entry.get("validado", False):
        return False
    ts_str = entry.get("created_at") or entry.get("updated_at") or ""
    if not ts_str:
        return False
    try:
        dt = datetime.datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        ref_now = now_ts if now_ts is not None else time.time()
        return (ref_now - dt.timestamp()) >= PENDING_TTL_SEC
    except Exception:
        return False


def _purgar_pendientes_vencidos_locked(acl: Dict[str, Any], vault: Optional[Dict[str, Any]] = None) -> bool:
    """Chequeo perezoso unificado (N1-b / N1-i): purga CUITs pendientes vencidos tanto de ACL como de credenciales.enc."""
    cuit_acl = acl.get("cuit_acl") or {}
    expired = [k for k, v in list(cuit_acl.items()) if _es_pendiente_vencido(v)]
    if not expired:
        return False
    for c in expired:
        cuit_acl.pop(c, None)
    _save_acl(acl)
    v = vault if vault is not None else _load_vault()
    vault_changed = False
    for c in expired:
        if c in v:
            v.pop(c, None)
            vault_changed = True
    if vault_changed:
        _save_vault(v)
    return True


def _pending_refresh_file() -> Path:
    """Archivo cifrado en VAULT_DIR para persistir cooldown de forzar_refresco en CUITs no validados (N1-i)."""
    return VAULT_DIR / "pending_refresh.enc"


def verificar_y_marcar_refresco_no_validado(
    cuit: str,
    cooldown_seg: float = 600.0,
    now_ts: Optional[float] = None,
) -> Tuple[bool, int]:
    """Limita `forzar_refresco` en CUITs no validados (N1-c / N1-i: máx. 1 cada 10 min, persistido en volumen)."""
    c = normalizar_cuit(cuit)
    if len(c) != 11:
        return True, 0
    now = now_ts if now_ts is not None else time.time()
    with _vault_io_lock:
        data = _read_enc_json(_pending_refresh_file(), {})
        if not isinstance(data, dict):
            data = {}
        data = {k: float(v) for k, v in data.items() if now - float(v) < 86400.0}
        last_ts = data.get(c)
        if last_ts is not None:
            elapsed = now - float(last_ts)
            if elapsed < cooldown_seg:
                return False, max(1, int(cooldown_seg - elapsed))
        data[c] = float(now)
        _write_enc_json(_pending_refresh_file(), data)
        return True, 0


def limpiar_refresco_no_validado(cuit: str) -> None:
    """Limpia el cooldown persistido de forzar_refresco tras validación exitosa."""
    c = normalizar_cuit(cuit)
    if len(c) != 11:
        return
    with _vault_io_lock:
        path = _pending_refresh_file()
        if not path.exists():
            return
        data = _read_enc_json(path, {})
        if isinstance(data, dict) and c in data:
            data.pop(c, None)
            _write_enc_json(path, data)


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _is_cloud_prod() -> bool:
    """O1 (fail-closed): producción por defecto; solo IMPUESTO_ENV=development|test relaja requisitos."""
    if (
        os.environ.get("OCI_REGION", "").strip()
        or os.environ.get("ORACLE_CLOUD", "").strip()
        or os.environ.get("FLY_APP_NAME", "").strip()
        or os.environ.get("REQUIRE_VAULT_KEY", "").strip() == "1"
    ):
        return True
    return os.environ.get("IMPUESTO_ENV", "").strip().lower() not in ("development", "test")


def _get_fernet() -> "Fernet":
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    env_key = os.environ.get("IMPUESTO_VAULT_KEY", "").strip()
    if env_key:
        raw = hashlib.sha256(env_key.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(raw)
    elif _is_cloud_prod():
        raise RuntimeError("IMPUESTO_VAULT_KEY es obligatoria en producción (no se autogenera clave local).")
    elif KEY_FILE.exists():
        key = KEY_FILE.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        KEY_FILE.write_bytes(key)
        os.chmod(KEY_FILE, 0o600)
    return Fernet(key)


def obtener_huella_vault_key() -> str:
    """Devuelve una huella corta (8 hex) de la clave maestra sin exponerla, para detectar rotación accidental."""
    env_key = os.environ.get("IMPUESTO_VAULT_KEY", "").strip()
    if env_key:
        return hashlib.sha256(env_key.encode("utf-8")).hexdigest()[:8]
    if KEY_FILE.exists():
        return hashlib.sha256(KEY_FILE.read_bytes().strip()).hexdigest()[:8]
    return "uninitialized"


def _read_enc_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    if not HAS_CRYPTO:
        raise RuntimeError("Falta librería 'cryptography' para operar la bóveda cifrada.")
    f = _get_fernet()
    try:
        data = f.decrypt(path.read_bytes())
    except InvalidToken as exc:
        if _is_cloud_prod() and KEY_FILE.exists():
            logger_boveda.critical(
                "O2: clave de bóveda distinta a la usada para cifrar (%s). Existe %s en volumen: "
                "corré `python3 scripts/migrar_clave_boveda.py --aplicar` antes de operar. NO se reescribirá el archivo.",
                path.name,
                KEY_FILE,
            )
        else:
            logger_boveda.critical(
                "O2: clave de bóveda distinta a la usada para cifrar (%s). NO se reescribirá el archivo.",
                path.name,
            )
        raise VaultKeyMismatchError(
            f"Clave de bóveda distinta a la usada para cifrar '{path.name}' (huella actual={obtener_huella_vault_key()})."
        ) from exc
    return json.loads(data.decode("utf-8"))


def _write_enc_json(path: Path, obj: Any) -> None:
    if not HAS_CRYPTO:
        raise RuntimeError("Falta librería 'cryptography' para operar la bóveda cifrada.")
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    f = _get_fernet()
    token = f.encrypt(json.dumps(obj, ensure_ascii=False).encode("utf-8"))
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}.{threading.get_ident()}")
    tmp.write_bytes(token)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


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

def crear_token_usuario(
    email: str,
    label: str = "principal",
    custom_token: Optional[str] = None,
    *,
    verificado: bool = False,
) -> Dict[str, Any]:
    """Crea un Personal Access Token (`imp_live_...` o frase clave personalizada >=16 chars) asociado a un email.
    Seguridad P0-1: si el email ya tiene cuenta o es super-admin, EXIGE `verificado=True` (vía OTP o sesión autenticada)."""
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
        # P0-1 cierre total: TODO token requiere identidad verificada (OTP o sesión autenticada previa),
        # incluso para emails nuevos (impide reclamar emails de contadores invitados como editor).
        if not verificado:
            return {
                "ok": False,
                "requiere_otp": True,
                "acceso_denegado": True,
                "error": (
                    "Para emitir un token de sesión primero debés verificar tu email con un código de 6 dígitos "
                    "(`solicitar_codigo_acceso_email` + `verificar_codigo_acceso_email`)."
                ),
            }
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
        _purgar_pendientes_vencidos_locked(acl, vault=vault)

        # N1-b: Solo las entradas VALIDADAS bloquean a otro email (o email vacío).
        # Una entrada pendiente_validacion (validado=False) NO bloquea a otro email verificado: se reemplaza.
        existing_acl = acl["cuit_acl"].get(cuit_clean)
        if existing_acl and existing_acl.get("owner_email"):
            is_val = bool(existing_acl.get("validado", False))
            if not em:
                return {
                    "ok": False,
                    "acceso_denegado": True,
                    "error": f"El CUIT {cuit_clean} requiere un email verificado para vincularse.",
                }
            if is_val and existing_acl["owner_email"] != em:
                return {
                    "ok": False,
                    "acceso_denegado": True,
                    "error": (
                        f"El CUIT {cuit_clean} ya tiene un propietario validado. "
                        "Iniciá sesión como Owner o pedile que te autorice por email (`autorizar_usuario_cuit`)."
                    ),
                }
            if not is_val and existing_acl["owner_email"] != em:
                # Reemplazar pendiente anterior por el nuevo email verificado
                acl["cuit_acl"].pop(cuit_clean, None)
                existing_acl = None

        prev_rec = vault.get(cuit_clean) or {}
        if existing_acl is None:
            prev_rec = {}
        clave_final = (clave_fiscal or "").strip() or prev_rec.get("clave_fiscal", "")
        vault[cuit_clean] = {
            "cuit": cuit_clean,
            "modo": modo,
            "alias": alias or prev_rec.get("alias") or f"Contribuyente {cuit_clean}",
            "clave_fiscal": clave_final,
            "tiene_wsaa": bool(cert_pem and key_pem) or prev_rec.get("tiene_wsaa", False),
            "cert_pem": cert_pem or prev_rec.get("cert_pem", ""),
            "key_pem": key_pem or prev_rec.get("key_pem", ""),
            "solo_lectura_por_defecto": True,
            "owner_email": em or (existing_acl or {}).get("owner_email", ""),
            "vinculado_at": ahora,
        }
        _save_vault(vault)

        if em:
            entry = acl["cuit_acl"].setdefault(
                cuit_clean,
                {"owner_email": em, "authorized": {}, "validado": False, "created_at": ahora},
            )
            if not entry.get("owner_email"):
                entry["owner_email"] = em
            entry.setdefault("validado", False)
            entry["updated_at"] = ahora
            _save_acl(acl)

    return {
        "ok": True,
        "cuit": cuit_clean,
        "owner_email": em or None,
        "estado_propiedad": "validado" if (existing_acl and existing_acl.get("validado")) else "pendiente_validacion",
        "modo": modo,
        "cifrado": "Fernet AES + HMAC-SHA256",
        "solo_lectura_por_defecto": True,
        "vinculado_at": ahora,
    }


def marcar_cuit_validado(
    cuit: str,
    email_actor: Optional[str] = None,
    clave_hash: Optional[str] = None,
    *,
    clave_fiscal: Optional[str] = None,
) -> bool:
    """Confirma la propiedad del CUIT tras un login exitoso en ARCA (cierre N1-g).

    - Valida solo si el owner actual y el hash de la clave guardada coinciden con el login exitoso.
    - Si NO coinciden (p. ej. un atacante pisó la entrada pendiente durante una carrera, o venció
      mientras el login corría), el login exitoso prueba la propiedad de `email_actor`: restaura
      a `email_actor` como owner validado con su `clave_fiscal` y descarta el reemplazo.
    - Si ya estaba validado y el actor es el owner o un usuario autorizado, conserva el owner vigente.
    """
    cuit_clean = normalizar_cuit(cuit)
    if len(cuit_clean) != 11:
        return False
    em_actor = normalizar_email(email_actor or "")
    clave_clean = (clave_fiscal or "").strip() if clave_fiscal is not None else None
    effective_hash = (clave_hash or "").strip()
    if not effective_hash and clave_clean:
        effective_hash = hash_clave_cuit(cuit_clean, clave_clean)
    ahora = _now_iso()

    with _vault_io_lock:
        acl = _load_acl()
        vault = _load_vault()
        entry = acl["cuit_acl"].get(cuit_clean)
        rec = vault.get(cuit_clean) or {}

        # Compatibilidad con llamadas internas/tests de 1 argumento (sin actor ni hash)
        if not em_actor and not effective_hash and clave_clean is None:
            if not entry:
                return False
            if not entry.get("validado"):
                entry["validado"] = True
                entry["validado_at"] = ahora
                entry["updated_at"] = ahora
                _save_acl(acl)
            return True

        # Si ya tiene un propietario validado: no pisar el owner cuando consulta el owner o un invitado autorizado
        if entry and entry.get("validado", False):
            if em_actor and (
                entry.get("owner_email") == em_actor
                or em_actor in (entry.get("authorized") or {})
            ):
                return True
            if not em_actor:
                return True
            return False

        clave_guardada = (rec.get("clave_fiscal") or "").strip()
        hash_guardado = hash_clave_cuit(cuit_clean, clave_guardada) if clave_guardada else ""
        owner_ok = bool(entry and (not em_actor or entry.get("owner_email") == em_actor))
        hash_ok = bool(
            not effective_hash
            or (hash_guardado and secrets.compare_digest(hash_guardado, effective_hash))
        )

        if owner_ok and hash_ok:
            entry["validado"] = True
            entry["validado_at"] = ahora
            entry["updated_at"] = ahora
            _save_acl(acl)
            return True

        # Mismatch en entrada pendiente/ausente: restaurar al actor que sí probó la clave en ARCA
        if not em_actor or not clave_clean:
            return False
        if effective_hash and not secrets.compare_digest(hash_clave_cuit(cuit_clean, clave_clean), effective_hash):
            return False

        same_prev_owner = rec.get("owner_email") == em_actor
        acl["cuit_acl"][cuit_clean] = {
            "owner_email": em_actor,
            "authorized": dict(entry.get("authorized") or {}) if (entry and entry.get("owner_email") == em_actor) else {},
            "validado": True,
            "created_at": ahora,
            "updated_at": ahora,
            "validado_at": ahora,
        }
        vault[cuit_clean] = {
            "cuit": cuit_clean,
            "modo": rec.get("modo", "solo_lectura_cifrada") if same_prev_owner else "solo_lectura_cifrada",
            "alias": (rec.get("alias") if same_prev_owner else None) or f"Contribuyente {cuit_clean}",
            "clave_fiscal": clave_clean,
            "tiene_wsaa": bool(rec.get("tiene_wsaa", False)) if same_prev_owner else False,
            "cert_pem": rec.get("cert_pem", "") if same_prev_owner else "",
            "key_pem": rec.get("key_pem", "") if same_prev_owner else "",
            "solo_lectura_por_defecto": True,
            "owner_email": em_actor,
            "vinculado_at": ahora,
        }
        _save_vault(vault)
        _save_acl(acl)
        return True


def liberar_cuit_pendiente(cuit: str, clave_fallida: Optional[str] = None) -> bool:
    """Si un CUIT estaba en pendiente_validacion y falló el login en ARCA, lo libera para no secuestrarlo (N1-b/N1-f)."""
    cuit_clean = normalizar_cuit(cuit)
    if len(cuit_clean) != 11:
        return False
    with _vault_io_lock:
        acl = _load_acl()
        entry = acl["cuit_acl"].get(cuit_clean)
        if not entry or entry.get("validado", False):
            return False
        vault = _load_vault()
        if clave_fallida is not None:
            rec = vault.get(cuit_clean) or {}
            if rec.get("clave_fiscal") and rec.get("clave_fiscal") != clave_fallida:
                return False
        acl["cuit_acl"].pop(cuit_clean, None)
        _save_acl(acl)
        if cuit_clean in vault:
            vault.pop(cuit_clean, None)
            _save_vault(vault)
        return True


def es_owner_validado(email: Optional[str], cuit: str) -> bool:
    """Devuelve True solo si `email` es owner de `cuit` Y ya superó al menos un login exitoso en ARCA."""
    em = normalizar_email(email or "")
    cuit_clean = normalizar_cuit(cuit)
    if not em or len(cuit_clean) != 11:
        return False
    with _vault_io_lock:
        acl = _load_acl()
        _purgar_pendientes_vencidos_locked(acl)
        entry = acl["cuit_acl"].get(cuit_clean)
        return bool(entry and entry.get("owner_email") == em and entry.get("validado", False))


def cargar_presupuesto_cuit() -> Dict[str, List[float]]:
    """Persistencia N1-d: lee el presupuesto de fallos por CUIT desde el volumen montado."""
    with _vault_io_lock:
        return _read_enc_json(VAULT_DIR / "cuit_budget.enc", {})


def guardar_presupuesto_cuit(data: Dict[str, List[float]]) -> None:
    """Persistencia N1-d: guarda el presupuesto de fallos por CUIT de forma atómica en el volumen."""
    with _vault_io_lock:
        _write_enc_json(VAULT_DIR / "cuit_budget.enc", data)


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
        _purgar_pendientes_vencidos_locked(acl)
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

        # N1-b: un owner pendiente de validación NO puede invitar terceros ni emitir comprobantes
        if nivel in ("owner", "escritura") and not entry.get("validado", False):
            return False, role, f"El CUIT {cuit_clean} está pendiente de validación en ARCA. Completá primero una consulta exitosa antes de invitar terceros o emitir."

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
        _purgar_pendientes_vencidos_locked(acl, vault=vault)
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
    raw = os.environ.get("PLATFORM_ADMIN_EMAILS", "").strip()
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
_otp_req_log: Dict[str, List[float]] = {}
_otp_daily_fails: Dict[str, List[float]] = {}
OTP_TTL_SEC = 600  # 10 minutos
OTP_MAX_REQ_15M = 3
OTP_MAX_FAILS_24H = 20


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


def es_email_verificado_conocido(email: str) -> bool:
    """True si `email` ya fue verificado previamente (tiene cuenta con token en ACL o es super-admin). Usado en N3-b."""
    em = normalizar_email(email)
    if not em:
        return False
    if es_admin_plataforma(em):
        return True
    with _vault_io_lock:
        acl = _load_acl()
        u = (acl.get("users") or {}).get(em)
        return bool(u and u.get("tokens"))


def solicitar_codigo_otp_email(email: str, client_ip: str = "unknown") -> Dict[str, Any]:
    """Genera un código OTP de 6 dígitos (SHA-256 en memoria, TTL 10 min) con límite en 3 niveles + protección N3-b."""
    from .limite_login import LIMITE_OTP_ENVIO

    em = normalizar_email(email)
    if "@" not in em or "." not in em.split("@")[-1]:
        return {"ok": False, "error": "Email inválido."}

    conocido = es_email_verificado_conocido(em)
    ok_lim, msg_lim = LIMITE_OTP_ENVIO.chequear(client_ip, em, es_usuario_conocido=conocido)
    if not ok_lim:
        return {"ok": False, "rate_limited": True, "error": msg_lim}
    LIMITE_OTP_ENVIO.registrar_fallo(client_ip, em)

    now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
    codigo = f"{secrets.randbelow(900000) + 100000}"
    exp = now_ts + OTP_TTL_SEC

    with _otp_lock:
        prev = _otp_store.get(em)
        prev_intentos = prev["intentos"] if (prev and now_ts <= prev["exp"]) else 0
        _otp_store[em] = {"hash": _hash_token(codigo), "exp": exp, "intentos": prev_intentos}

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
                    "Mientras tanto, iniciá sesión en el chat con tu frase clave (`iniciar_sesion_en_chat`)."
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


def verificar_codigo_otp_email(email: str, codigo: str, origen_llm: str = "mcp", client_ip: str = "unknown") -> Dict[str, Any]:
    """Verifica el código OTP de 6 dígitos (uso único, máx 5 intentos + límite 3 niveles sin DoS de 24h) y emite token_sesion."""
    from .limite_login import LIMITE_OTP_VERIF

    em = normalizar_email(email)
    cod = "".join(ch for ch in str(codigo or "") if ch.isdigit())
    if "@" not in em or len(cod) != 6:
        return {"ok": False, "acceso_denegado": True, "error": "Indicá tu email y el código numérico de 6 dígitos."}

    ok_lim, msg_lim = LIMITE_OTP_VERIF.chequear(client_ip, em)
    if not ok_lim:
        return {"ok": False, "acceso_denegado": True, "rate_limited": True, "error": msg_lim}

    now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
    with _otp_lock:
        rec = _otp_store.get(em)
        if not rec:
            LIMITE_OTP_VERIF.registrar_fallo(client_ip, em)
            return {"ok": False, "acceso_denegado": True, "error": "No hay un código activo para ese email. Pedí uno nuevo."}
        if now_ts > rec["exp"]:
            _otp_store.pop(em, None)
            LIMITE_OTP_VERIF.registrar_fallo(client_ip, em)
            return {"ok": False, "acceso_denegado": True, "error": "El código venció (superó los 10 minutos). Pedí uno nuevo."}
        rec["intentos"] += 1
        if rec["intentos"] > 5:
            _otp_store.pop(em, None)
            LIMITE_OTP_VERIF.registrar_fallo(client_ip, em)
            return {"ok": False, "acceso_denegado": True, "error": "Demasiados intentos fallidos. Pedí un código nuevo."}
        if not secrets.compare_digest(rec["hash"], _hash_token(cod)):
            LIMITE_OTP_VERIF.registrar_fallo(client_ip, em)
            return {"ok": False, "acceso_denegado": True, "error": "Código incorrecto. Verificá los 6 dígitos en tu correo."}
        # Uso único: consumir el OTP
        _otp_store.pop(em, None)

    LIMITE_OTP_VERIF.registrar_exito(client_ip, em)
    tok = crear_token_usuario(email=em, label=f"otp_{origen_llm}", verificado=True)
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
