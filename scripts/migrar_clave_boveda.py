#!/usr/bin/env python3
"""
scripts/migrar_clave_boveda.py
Migra la bóveda cifrada de impuesto.com.ar desde `.vault_key` local hacia `IMPUESTO_VAULT_KEY` (cierre O2/O2-b/O2-c).

Características:
  - Modo `--dry-run` por defecto (no modifica archivos). `--aplicar` ejecuta la migración.
  - Backup persistente dentro de `<vault_dir>/_backups_o2/<ts>` por defecto (excluido de migraciones futuras),
    o en `--backup-dir`. Dentro de Docker (`/.dockerenv`), exige que el backup quede bajo `/app/data/boveda`.
  - Migración en dos fases (atómica): cifra y verifica TODOS los archivos en `<vault_dir>/.mig_tmp_<ts>/`
    antes de hacer `os.replace` sobre los originales. Si algo falla antes, no se toca ningún original.
  - Retomable: si un archivo ya abre con `IMPUESTO_VAULT_KEY`, se saltea; si no abre ni con `.vault_key`
    ni con `IMPUESTO_VAULT_KEY`, aborta indicando el nombre del archivo.
  - Imprime únicamente huellas cortas (SHA-256 8 hex), NUNCA las claves.
"""

import argparse
import base64
import datetime
import hashlib
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cryptography.fernet import Fernet, InvalidToken

BACKUP_SUBDIR = "_backups_o2"
STAGE_PREFIX = ".mig_tmp_"


def _fernet_from_env_key(env_key: str) -> Fernet:
    raw = hashlib.sha256(env_key.strip().encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(raw))


def _huella_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:8]


def _huella_str(s: str) -> str:
    return hashlib.sha256(s.strip().encode("utf-8")).hexdigest()[:8]


def _es_ruta_excluida(rel_parts: tuple) -> bool:
    for part in rel_parts:
        if part == BACKUP_SUBDIR or part.startswith(STAGE_PREFIX):
            return True
    return False


def _listar_enc_activos(vdir: Path) -> List[Path]:
    out = []
    for p in sorted(vdir.rglob("*.enc")):
        rel = p.relative_to(vdir)
        if _es_ruta_excluida(rel.parts):
            continue
        out.append(p)
    return out


def _validar_backup_dir_en_docker(backup_dir: Path) -> None:
    if Path("/.dockerenv").exists():
        vol_root = Path("/app/data/boveda").resolve()
        try:
            backup_dir.resolve().relative_to(vol_root)
        except ValueError as exc:
            raise RuntimeError(
                f"O2-c: dentro de Docker el backup ({backup_dir}) debe quedar dentro del volumen persistente "
                f"({vol_root}) para no perderse al terminar el contenedor."
            ) from exc


def migrar_boveda(
    vault_dir: Path,
    new_env_key: str,
    *,
    aplicar: bool = False,
    backup_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Migra todos los `*.enc` activos dentro de `vault_dir` desde `.vault_key` hacia `new_env_key`."""
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

    enc_files = _listar_enc_activos(vdir)
    if not enc_files:
        return {
            "ok": True,
            "dry_run": not aplicar,
            "huella_anterior": huella_vieja,
            "huella_nueva": huella_nueva,
            "archivos_encontrados": 0,
            "migrados": [],
            "ya_migrados": [],
            "backup_dir": None,
        }

    # Fase 1: descifrar y clasificar (retomable: acepta clave vieja o clave nueva si ya fue migrado)
    pendientes: List[tuple[Path, bytes]] = []
    ya_migrados: List[str] = []
    for p in enc_files:
        rel_str = str(p.relative_to(vdir))
        raw_ct = p.read_bytes()
        try:
            plain = f_old.decrypt(raw_ct)
            pendientes.append((p, plain))
        except InvalidToken:
            try:
                f_new.decrypt(raw_ct)
                ya_migrados.append(rel_str)
            except InvalidToken as exc:
                raise RuntimeError(
                    f"No se pudo descifrar '{rel_str}' ni con .vault_key ({huella_vieja}) ni con IMPUESTO_VAULT_KEY ({huella_nueva}). "
                    "Abortando sin modificar ningún archivo."
                ) from exc

    if not aplicar:
        return {
            "ok": True,
            "dry_run": True,
            "huella_anterior": huella_vieja,
            "huella_nueva": huella_nueva,
            "archivos_encontrados": len(enc_files),
            "pendientes": [str(p.relative_to(vdir)) for p, _ in pendientes],
            "ya_migrados": ya_migrados,
            "backup_dir": None,
        }

    # Backup persistente (por defecto dentro de <vault_dir>/_backups_o2/<ts>)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    bdir = Path(backup_dir).resolve() if backup_dir else (vdir / BACKUP_SUBDIR / ts)
    _validar_backup_dir_en_docker(bdir)
    bdir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        vdir,
        bdir,
        ignore=lambda _src, names: [n for n in names if n == BACKUP_SUBDIR or n.startswith(STAGE_PREFIX)],
    )

    # Fase 2 (atómica): cifrar y verificar TODO en directorio temporal dentro de vault_dir antes de tocar originales
    stage_dir = vdir / f"{STAGE_PREFIX}{ts}_{os.getpid()}"
    stage_dir.mkdir(parents=True, exist_ok=True)
    staged_pairs: List[tuple[Path, Path]] = []
    try:
        for p, plain in pendientes:
            rel = p.relative_to(vdir)
            staged_path = stage_dir / rel
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            new_ct = f_new.encrypt(plain)
            staged_path.write_bytes(new_ct)
            os.chmod(staged_path, 0o600)
            if f_new.decrypt(staged_path.read_bytes()) != plain:
                raise RuntimeError(f"Verificación post-cifrado falló para '{rel}'.")
            staged_pairs.append((staged_path, p))

        # Fase 3: reemplazo atómico una vez que TODOS los archivos se cifraron y verificaron con éxito
        migrados: List[str] = []
        for staged_path, orig_path in staged_pairs:
            os.replace(staged_path, orig_path)
            migrados.append(str(orig_path.relative_to(vdir)))
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)

    # Fase 4: renombrar .vault_key -> .vault_key.migrada
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
        "ya_migrados": ya_migrados,
        "backup_dir": str(bdir),
        "vault_key_renombrada": str(migrated_key_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Migra archivos *.enc de .vault_key a IMPUESTO_VAULT_KEY (O2).")
    parser.add_argument("--vault-dir", default=str(ROOT / "data" / "boveda"), help="Ruta de VAULT_DIR (default: data/boveda)")
    parser.add_argument("--backup-dir", default="", help="Ruta de backup (default: <vault-dir>/_backups_o2/<ts>)")
    parser.add_argument("--aplicar", action="store_true", help="Ejecuta backup y migración real (sin este flag corre en --dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="Simula y verifica descifrado sin modificar archivos (comportamiento por defecto)")
    args = parser.parse_args()

    aplicar = bool(args.aplicar and not args.dry_run)
    env_key = os.environ.get("IMPUESTO_VAULT_KEY", "").strip()
    bdir = Path(args.backup_dir) if args.backup_dir.strip() else None
    res = migrar_boveda(Path(args.vault_dir), env_key, aplicar=aplicar, backup_dir=bdir)
    modo = "APLICADO" if not res["dry_run"] else "DRY-RUN (sin cambios; usá --aplicar para ejecutar)"
    print(f"[O2 migración bóveda — {modo}]")
    print(f"  Huella clave anterior (.vault_key): {res['huella_anterior']}")
    print(f"  Huella clave nueva (IMPUESTO_VAULT_KEY): {res['huella_nueva']}")
    print(f"  Archivos *.enc verificados: {res['archivos_encontrados']} (ya migrados: {len(res.get('ya_migrados', []))})")
    if res.get("backup_dir"):
        print(f"  Backup persistente creado en: {res['backup_dir']}")
    if res.get("vault_key_renombrada"):
        print(f"  .vault_key renombrada a: {res['vault_key_renombrada']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
