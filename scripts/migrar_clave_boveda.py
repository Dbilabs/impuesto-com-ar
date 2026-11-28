#!/usr/bin/env python3
"""
scripts/migrar_clave_boveda.py
Migra la bóveda cifrada de impuesto.com.ar desde `.vault_key` local hacia `IMPUESTO_VAULT_KEY` (cierre O2).

Pasos que realiza:
  1. Backup completo con fecha de VAULT_DIR (solo con --aplicar).
  2. Descifra cada archivo `*.enc` (incluido `wsaa_cache/*.enc`) con la clave de `.vault_key`.
  3. Vuelve a cifrar con `sha256(IMPUESTO_VAULT_KEY)` usando escritura atómica y permisos 0600.
  4. Verifica que cada archivo migrado se lea correctamente con la clave nueva.
  5. Renombra `.vault_key` a `.vault_key.migrada`.
  6. Imprime únicamente huellas cortas (SHA-256 8 hex), NUNCA las claves.

Uso:
  python3 scripts/migrar_clave_boveda.py                  # --dry-run por defecto (no modifica nada)
  python3 scripts/migrar_clave_boveda.py --aplicar        # ejecuta backup + migración
  python3 scripts/migrar_clave_boveda.py --vault-dir /var/lib/impuesto/boveda --aplicar
"""

import argparse
import base64
import datetime
import hashlib
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cryptography.fernet import Fernet, InvalidToken


def _fernet_from_env_key(env_key: str) -> Fernet:
    raw = hashlib.sha256(env_key.strip().encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(raw))


def _huella_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:8]


def _huella_str(s: str) -> str:
    return hashlib.sha256(s.strip().encode("utf-8")).hexdigest()[:8]


def migrar_boveda(
    vault_dir: Path,
    new_env_key: str,
    *,
    aplicar: bool = False,
) -> Dict[str, Any]:
    """Migra todos los `*.enc` dentro de `vault_dir` (recursivo) desde `.vault_key` hacia `new_env_key`."""
    vdir = Path(vault_dir).resolve()
    key_file = vdir / ".vault_key"
    env_k = (new_env_key or "").strip()

    if not env_k:
        raise RuntimeError("IMPUESTO_VAULT_KEY no está definida en el entorno.")
    if not vdir.exists():
        raise FileNotFoundError(f"No existe el directorio de bóveda: {vdir}")
    if not key_file.exists():
        raise FileNotFoundError(f"No existe {key_file}. Si ya fue migrada, verificá .vault_key.migrada.")

    old_raw = key_file.read_bytes().strip()
    f_old = Fernet(old_raw)
    f_new = _fernet_from_env_key(env_k)
    huella_vieja = _huella_bytes(old_raw)
    huella_nueva = _huella_str(env_k)

    enc_files: List[Path] = sorted(vdir.rglob("*.enc"))
    if not enc_files:
        return {
            "ok": True,
            "dry_run": not aplicar,
            "huella_anterior": huella_vieja,
            "huella_nueva": huella_nueva,
            "archivos_encontrados": 0,
            "migrados": [],
            "backup_dir": None,
        }

    # Paso 2 (validación previa tanto en dry-run como en --aplicar): descifrar TODO antes de escribir nada
    decrypted_payloads: List[tuple[Path, bytes]] = []
    for p in enc_files:
        raw_ct = p.read_bytes()
        try:
            plain = f_old.decrypt(raw_ct)
        except InvalidToken as exc:
            raise RuntimeError(
                f"No se pudo descifrar {p.relative_to(vdir)} con .vault_key (huella={huella_vieja}). "
                "Abortando sin modificar ningún archivo."
            ) from exc
        decrypted_payloads.append((p, plain))

    if not aplicar:
        return {
            "ok": True,
            "dry_run": True,
            "huella_anterior": huella_vieja,
            "huella_nueva": huella_nueva,
            "archivos_encontrados": len(enc_files),
            "archivos": [str(p.relative_to(vdir)) for p in enc_files],
            "backup_dir": None,
        }

    # Paso 1: backup completo con fecha antes de tocar nada
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir = vdir.parent / f"{vdir.name}_backup_{ts}"
    shutil.copytree(vdir, backup_dir)

    # Paso 3: re-cifrar con escritura atómica y permisos 0600
    migrados: List[str] = []
    for p, plain in decrypted_payloads:
        new_ct = f_new.encrypt(plain)
        tmp = p.with_suffix(p.suffix + f".mig.{os.getpid()}")
        tmp.write_bytes(new_ct)
        os.chmod(tmp, 0o600)
        os.replace(tmp, p)
        # Paso 4: verificar lectura inmediata con la clave nueva
        if f_new.decrypt(p.read_bytes()) != plain:
            raise RuntimeError(f"Verificación post-migración falló para {p.name}.")
        migrados.append(str(p.relative_to(vdir)))

    # Paso 5: renombrar .vault_key -> .vault_key.migrada
    migrated_key_path = vdir / ".vault_key.migrada"
    os.replace(key_file, migrated_key_path)
    os.chmod(migrated_key_path, 0o600)

    return {
        "ok": True,
        "dry_run": False,
        "huella_anterior": huella_vieja,
        "huella_nueva": huella_nueva,
        "archivos_encontrados": len(enc_files),
        "migrados": migrados,
        "backup_dir": str(backup_dir),
        "vault_key_renombrada": str(migrated_key_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Migra archivos *.enc de .vault_key a IMPUESTO_VAULT_KEY (O2).")
    parser.add_argument("--vault-dir", default=str(ROOT / "data" / "boveda"), help="Ruta de VAULT_DIR (default: data/boveda)")
    parser.add_argument("--aplicar", action="store_true", help="Ejecuta backup y migración real (sin este flag corre en --dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="Simula y verifica descifrado sin modificar archivos (comportamiento por defecto)")
    args = parser.parse_args()

    aplicar = bool(args.aplicar and not args.dry_run)
    env_key = os.environ.get("IMPUESTO_VAULT_KEY", "").strip()
    res = migrar_boveda(Path(args.vault_dir), env_key, aplicar=aplicar)
    modo = "APLICADO" if not res["dry_run"] else "DRY-RUN (sin cambios; usá --aplicar para ejecutar)"
    print(f"[O2 migración bóveda — {modo}]")
    print(f"  Huella clave anterior (.vault_key): {res['huella_anterior']}")
    print(f"  Huella clave nueva (IMPUESTO_VAULT_KEY): {res['huella_nueva']}")
    print(f"  Archivos *.enc verificados: {res['archivos_encontrados']}")
    if res.get("backup_dir"):
        print(f"  Backup creado en: {res['backup_dir']}")
    if res.get("vault_key_renombrada"):
        print(f"  .vault_key renombrada a: {res['vault_key_renombrada']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
