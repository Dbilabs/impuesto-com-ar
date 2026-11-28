#!/usr/bin/env python3
"""
scripts/migrar_clave_boveda.py
Wrapper de compatibilidad; la implementación canónica vive en `bot/migrar_clave_boveda.py`
(incluida en la imagen Docker para ejecutarse con `python3 -m bot.migrar_clave_boveda`).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot import migrar_clave_boveda as _impl  # noqa: E402

_fernet_from_env_key = _impl._fernet_from_env_key
main = _impl.main


def migrar_boveda(*args, **kwargs):
    orig = _impl._fernet_from_env_key
    _impl._fernet_from_env_key = _fernet_from_env_key
    try:
        return _impl.migrar_boveda(*args, **kwargs)
    finally:
        _impl._fernet_from_env_key = orig


if __name__ == "__main__":
    raise SystemExit(main())
